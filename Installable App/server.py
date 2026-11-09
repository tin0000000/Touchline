from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if os.environ.get("TOUCHLINE_DB_PATH"):
    DB = Path(os.environ["TOUCHLINE_DB_PATH"]).expanduser().resolve()
else:
    DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "Touchline"
    DB = DATA_ROOT / "touchline.sqlite3"
LEGACY_DB = ROOT / "touchline-accounts.sqlite3"
MAX_BODY = 12 * 1024 * 1024
SESSION_DAYS = 30
PBKDF2_ROUNDS = 310_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def migrate_legacy_database() -> None:
    if DB.exists() or not LEGACY_DB.exists():
        return
    DB.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(LEGACY_DB, timeout=10)
    destination = sqlite3.connect(DB, timeout=10)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def connect() -> sqlite3.Connection:
    migrate_legacy_database()
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 10000")
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            email TEXT PRIMARY KEY,
            salt BLOB NOT NULL,
            password_hash BLOB NOT NULL,
            data TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            email TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL DEFAULT ''
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            owner_email TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
            name TEXT NOT NULL,
            invite_code TEXT NOT NULL UNIQUE,
            data TEXT NOT NULL DEFAULT '{}',
            revision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            email TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('manager','player')),
            player_id TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL,
            PRIMARY KEY(team_id,email)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS team_members_email_idx ON team_members(email)")
    db.execute("""CREATE TABLE IF NOT EXISTS players (
        team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE, player_id TEXT NOT NULL,
        name TEXT NOT NULL, jersey_number TEXT NOT NULL DEFAULT '', positions TEXT NOT NULL DEFAULT '[]',
        stats TEXT NOT NULL DEFAULT '{}', data TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(team_id,player_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS fixtures (
        team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE, fixture_id TEXT NOT NULL,
        kickoff TEXT NOT NULL DEFAULT '', opponent TEXT NOT NULL DEFAULT '', data TEXT NOT NULL,
        PRIMARY KEY(team_id,fixture_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS matches (
        team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE, match_id TEXT NOT NULL,
        status TEXT NOT NULL, opponent TEXT NOT NULL DEFAULT '', home_score INTEGER NOT NULL DEFAULT 0,
        away_score INTEGER NOT NULL DEFAULT 0, period TEXT NOT NULL DEFAULT 'first', clock INTEGER NOT NULL DEFAULT 0,
        data TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(team_id,match_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS match_events (
        team_id TEXT NOT NULL, match_id TEXT NOT NULL, event_id TEXT NOT NULL, minute INTEGER NOT NULL DEFAULT 0,
        event_type TEXT NOT NULL, team_side TEXT NOT NULL DEFAULT 'home', player_id TEXT NOT NULL DEFAULT '',
        assist_id TEXT NOT NULL DEFAULT '', data TEXT NOT NULL,
        PRIMARY KEY(team_id,match_id,event_id),
        FOREIGN KEY(team_id,match_id) REFERENCES matches(team_id,match_id) ON DELETE CASCADE)""")
    db.execute("CREATE INDEX IF NOT EXISTS match_events_timeline_idx ON match_events(team_id,match_id,minute)")
    # Upgrade databases from earlier Touchline builds without losing existing accounts.
    account_columns = {row[1] for row in db.execute("PRAGMA table_info(accounts)")}
    for column in ("created_at", "updated_at"):
        if column not in account_columns:
            db.execute(f"ALTER TABLE accounts ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    session_columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
    for column in ("created_at", "expires_at"):
        if column not in session_columns:
            db.execute(f"ALTER TABLE sessions ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    for column, definition in (("role", "TEXT NOT NULL DEFAULT 'manager'"),
                               ("display_name", "TEXT NOT NULL DEFAULT ''"),
                               ("player_id", "TEXT NOT NULL DEFAULT ''")):
        if column not in account_columns:
            db.execute(f"ALTER TABLE accounts ADD COLUMN {column} {definition}")
    return db


def new_invite_code(db: sqlite3.Connection) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not db.execute("SELECT 1 FROM teams WHERE invite_code=?", (code,)).fetchone():
            return code


def persist_team_snapshots(db: sqlite3.Connection, email: str, snapshot: dict) -> None:
    """Mirror each account's team workspace into shared, revisioned team records."""
    profiles = snapshot.get("teamProfiles")
    if not isinstance(profiles, list):
        profiles = []
    active_id = str(snapshot.get("activeTeamId", ""))
    account = snapshot.get("account") or {}
    role = "player" if account.get("role") == "player" else "manager"
    player_id = str(account.get("playerId") or "")
    now = utc_now()
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        team_id = str(profile.get("id", "")).strip()
        if not team_id:
            continue
        team_data = profile.get("data")
        if team_id == active_id or not isinstance(team_data, dict):
            team_data = {k: v for k, v in snapshot.items() if k not in ("teamProfiles", "account")}
        name = str(profile.get("name") or team_data.get("club") or "Untitled club").strip()[:100]
        existing = db.execute("SELECT owner_email FROM teams WHERE id=?", (team_id,)).fetchone()
        if existing and existing[0] != email:
            membership = db.execute("SELECT role FROM team_members WHERE team_id=? AND email=?", (team_id,email)).fetchone()
            # Managers explicitly added by invite can maintain shared team records; players are read-only.
            if not membership or membership[0] != "manager":
                continue
        if existing:
            db.execute("UPDATE teams SET name=?,data=?,revision=revision+1,updated_at=? WHERE id=?",
                       (name, json.dumps(team_data, separators=(",", ":")), now, team_id))
        else:
            invite = new_invite_code(db)
            db.execute("INSERT INTO teams(id,owner_email,name,invite_code,data,revision,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)",
                       (team_id, email, name, invite, json.dumps(team_data, separators=(",", ":")), now, now))
        db.execute("INSERT INTO team_members(team_id,email,role,player_id,joined_at) VALUES(?,?,?,?,?) "
                   "ON CONFLICT(team_id,email) DO UPDATE SET role=excluded.role,player_id=excluded.player_id",
                   (team_id, email, role, player_id, now))
        # Keep queryable football records alongside the backward-compatible workspace JSON.
        db.execute("DELETE FROM players WHERE team_id=?", (team_id,))
        for player in team_data.get("players", []) if isinstance(team_data.get("players"), list) else []:
            if not isinstance(player, dict):
                continue
            pid = str(player.get("id", ""))
            if not pid:
                continue
            positions = player.get("positions") or [player.get("pos", "")]
            db.execute("INSERT INTO players(team_id,player_id,name,jersey_number,positions,stats,data,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                       (team_id,pid,str(player.get("name", "")),str(player.get("number", "")),
                        json.dumps(positions),json.dumps(player.get("stats", {})),json.dumps(player),now))
        db.execute("DELETE FROM fixtures WHERE team_id=?", (team_id,))
        for fixture in team_data.get("fixtures", []) if isinstance(team_data.get("fixtures"), list) else []:
            if isinstance(fixture, dict) and fixture.get("id") is not None:
                db.execute("INSERT INTO fixtures(team_id,fixture_id,kickoff,opponent,data) VALUES(?,?,?,?,?)",
                           (team_id,str(fixture["id"]),str(fixture.get("date", "")+" "+fixture.get("time", "")),
                            str(fixture.get("opponent", "")),json.dumps(fixture)))
        db.execute("DELETE FROM matches WHERE team_id=?", (team_id,))
        match_rows = []
        for match in team_data.get("history", []) if isinstance(team_data.get("history"), list) else []:
            if isinstance(match, dict) and match.get("id") is not None:
                match_rows.append((str(match["id"]), "complete", match))
        if team_data.get("matchStarted") and not team_data.get("matchSaved"):
            match_rows.append(("live-current", "live" if team_data.get("live") else "paused", team_data))
        for mid, status, match in match_rows:
            score = match.get("score") if isinstance(match.get("score"), list) else [match.get("home", 0),match.get("away", 0)]
            db.execute("INSERT INTO matches(team_id,match_id,status,opponent,home_score,away_score,period,clock,data,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (team_id,mid,status,str(match.get("opponent", "")),int(score[0] or 0),int(score[1] or 0),
                        str(match.get("matchPeriod", "full" if status=="complete" else "first")),int(match.get("clock", 0) or 0),json.dumps(match),now))
            for event in match.get("events", []) if isinstance(match.get("events"), list) else []:
                if not isinstance(event, dict):
                    continue
                eid = str(event.get("id", ""))
                if not eid:
                    continue
                db.execute("INSERT INTO match_events(team_id,match_id,event_id,minute,event_type,team_side,player_id,assist_id,data) VALUES(?,?,?,?,?,?,?,?,?)",
                           (team_id,mid,eid,int(event.get("min", 0) or 0),str(event.get("type", "event")),
                            str(event.get("team", "home")),str(event.get("playerId", "")),str(event.get("assistId", "")),json.dumps(event)))


def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(db: sqlite3.Connection, email: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.execute("INSERT INTO sessions(token_hash,email,created_at,expires_at) VALUES(?,?,?,?)",
               (token_hash(token), email, now.isoformat(timespec="microseconds"),
                (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="microseconds")))
    return token


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print("[Touchline] " + fmt % args)

    def send_json(self, status: int, data: dict):
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise ValueError("Request is too large")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    def email_for_token(self):
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not token:
            return None
        now = utc_now()
        with connect() as db:
            row = db.execute("SELECT email FROM sessions WHERE token_hash=? AND expires_at>?",
                             (token_hash(token), now)).fetchone()
            db.execute("DELETE FROM sessions WHERE expires_at<=? OR expires_at=''", (now,))
        return row[0] if row else None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route.lower().endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm")):
            return self.send_error(404)
        if route == "/api/health":
            return self.send_json(200, {"ok": True, "storage": "sqlite", "database": "ready"})
        if route == "/api/teams":
            email = self.email_for_token()
            if not email:
                return self.send_json(401, {"error": "Sign in required"})
            with connect() as db:
                rows = db.execute("""SELECT t.id,t.name,CASE WHEN t.owner_email=? THEN t.invite_code ELSE '' END,t.revision,t.updated_at,m.role,m.player_id,
                    (t.owner_email=m.email) AS is_owner FROM team_members m JOIN teams t ON t.id=m.team_id
                    WHERE m.email=? ORDER BY t.name COLLATE NOCASE""", (email,email)).fetchall()
            keys = ("id","name","inviteCode","revision","updatedAt","role","playerId","isOwner")
            return self.send_json(200, {"teams": [dict(zip(keys, r)) for r in rows]})
        if route.startswith("/api/teams/") and route.endswith("/data"):
            email = self.email_for_token()
            if not email:
                return self.send_json(401, {"error": "Sign in required"})
            team_id = route[len("/api/teams/"):-len("/data")].strip("/")
            with connect() as db:
                row = db.execute("""SELECT t.data,t.revision,t.updated_at,m.role,m.player_id FROM teams t
                    JOIN team_members m ON m.team_id=t.id WHERE t.id=? AND m.email=?""", (team_id, email)).fetchone()
            if not row:
                return self.send_json(404, {"error": "Team not found or you are not a member"})
            return self.send_json(200, {"data": row[0], "revision": row[1], "updatedAt": row[2], "role": row[3], "playerId": row[4]})
        if route.startswith("/api/teams/") and route.endswith("/records"):
            email = self.email_for_token()
            if not email:
                return self.send_json(401, {"error": "Sign in required"})
            team_id = route[len("/api/teams/"):-len("/records")].strip("/")
            with connect() as db:
                access = db.execute("SELECT 1 FROM team_members WHERE team_id=? AND email=?", (team_id,email)).fetchone()
                if not access:
                    return self.send_json(404, {"error": "Team not found or you are not a member"})
                players = db.execute("SELECT player_id,name,jersey_number,positions,stats,data FROM players WHERE team_id=? ORDER BY name COLLATE NOCASE", (team_id,)).fetchall()
                fixtures = db.execute("SELECT fixture_id,kickoff,opponent,data FROM fixtures WHERE team_id=? ORDER BY kickoff", (team_id,)).fetchall()
                matches = db.execute("SELECT match_id,status,opponent,home_score,away_score,period,clock,data FROM matches WHERE team_id=? ORDER BY updated_at DESC", (team_id,)).fetchall()
                events = db.execute("SELECT match_id,event_id,minute,event_type,team_side,player_id,assist_id,data FROM match_events WHERE team_id=? ORDER BY match_id,minute,event_id", (team_id,)).fetchall()
            parse = lambda value: json.loads(value)
            return self.send_json(200, {
                "players": [{"id":r[0],"name":r[1],"number":r[2],"positions":parse(r[3]),"stats":parse(r[4]),"data":parse(r[5])} for r in players],
                "fixtures": [{"id":r[0],"kickoff":r[1],"opponent":r[2],"data":parse(r[3])} for r in fixtures],
                "matches": [{"id":r[0],"status":r[1],"opponent":r[2],"home":r[3],"away":r[4],"period":r[5],"clock":r[6],"data":parse(r[7])} for r in matches],
                "events": [{"matchId":r[0],"id":r[1],"minute":r[2],"type":r[3],"team":r[4],"playerId":r[5],"assistId":r[6],"data":parse(r[7])} for r in events]
            })
        if route.startswith("/api/teams/") and route.endswith("/members"):
            email = self.email_for_token()
            if not email:
                return self.send_json(401, {"error": "Sign in required"})
            team_id = route[len("/api/teams/"):-len("/members")].strip("/")
            with connect() as db:
                access = db.execute("SELECT role FROM team_members WHERE team_id=? AND email=?", (team_id,email)).fetchone()
                if not access:
                    return self.send_json(404, {"error": "Team not found or you are not a member"})
                owner = db.execute("SELECT owner_email FROM teams WHERE id=?", (team_id,)).fetchone()[0]
                if owner != email:
                    return self.send_json(403, {"error": "Only the team owner can view member emails"})
                rows = db.execute("SELECT email,role,player_id,joined_at FROM team_members WHERE team_id=? ORDER BY role,email", (team_id,)).fetchall()
            keys = ("email","role","playerId","joinedAt")
            return self.send_json(200, {"members": [dict(zip(keys,r)) for r in rows]})
        if route == "/api/sync":
            email = self.email_for_token()
            if not email:
                return self.send_json(401, {"error": "Sign in required"})
            with connect() as db:
                row = db.execute("SELECT data,updated_at FROM accounts WHERE email=?", (email,)).fetchone()
            return self.send_json(200, {"data": row[0] if row else "", "updatedAt": row[1] if row else ""})
        return super().do_GET()

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        try:
            body = self.read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"error": str(exc) or "Invalid JSON"})

        if route == "/api/register":
            email = str(body.get("email", "")).strip().lower()
            password = str(body.get("password", ""))
            role = "player" if body.get("role") == "player" else "manager"
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
                return self.send_json(400, {"error": "Enter a valid email address"})
            if len(password) < 8 or len(password) > 1024:
                return self.send_json(400, {"error": "Password must be at least 8 characters"})
            salt = secrets.token_bytes(16)
            now = utc_now()
            try:
                with connect() as db:
                    db.execute("INSERT INTO accounts(email,salt,password_hash,data,created_at,updated_at,role,display_name,player_id) VALUES(?,?,?,?,?,?,?,?,?)",
                               (email, salt, hash_password(password, salt), "", now, "", role,
                                str(body.get("displayName", ""))[:100], str(body.get("playerId", ""))))
                    token = issue_session(db, email)
            except sqlite3.IntegrityError:
                return self.send_json(409, {"error": "An account with that email already exists. Sign in instead."})
            return self.send_json(201, {"token": token, "data": "", "updatedAt": "", "role": role})

        if route == "/api/login":
            email = str(body.get("email", "")).strip().lower()
            password = str(body.get("password", ""))
            if len(password) > 1024:
                return self.send_json(401, {"error": "Email or password is incorrect"})
            with connect() as db:
                row = db.execute("SELECT salt,password_hash,data,updated_at,role,display_name,player_id FROM accounts WHERE email=?", (email,)).fetchone()
                if not row or not secrets.compare_digest(hash_password(password, row[0]), row[1]):
                    return self.send_json(401, {"error": "Email or password is incorrect"})
                token = issue_session(db, email)
            return self.send_json(200, {"token": token, "data": row[2], "updatedAt": row[3], "role": row[4], "displayName": row[5], "playerId": row[6]})

        if route == "/api/sync":
            email = self.email_for_token()
            if not email:
                return self.send_json(401, {"error": "Sign in required"})
            data = body.get("data", "")
            if not isinstance(data, str) or len(data.encode("utf-8")) > MAX_BODY:
                return self.send_json(413, {"error": "Backup is too large"})
            try:
                parsed = json.loads(data)
                if not isinstance(parsed, dict):
                    raise ValueError("Expected an account snapshot")
            except (ValueError, json.JSONDecodeError):
                return self.send_json(400, {"error": "Invalid backup data"})
            base_version = body.get("baseUpdatedAt")
            now = utc_now()
            with connect() as db:
                current = db.execute("SELECT updated_at FROM accounts WHERE email=?", (email,)).fetchone()
                if not current:
                    return self.send_json(401, {"error": "Account no longer exists"})
                current_version = current[0] or ""
                if base_version is not None and str(base_version) != current_version:
                    remote = db.execute("SELECT data FROM accounts WHERE email=?", (email,)).fetchone()[0]
                    return self.send_json(409, {"error": "Account data changed on another device", "data": remote,
                                                "updatedAt": current_version})
                persist_team_snapshots(db, email, parsed)
                account_profile = parsed.get("account") or {}
                role = "player" if account_profile.get("role") == "player" else "manager"
                db.execute("UPDATE accounts SET data=?,updated_at=?,role=?,display_name=?,player_id=? WHERE email=?",
                           (data, now, role, str(account_profile.get("displayName", ""))[:100],
                            str(account_profile.get("playerId", "")), email))
            return self.send_json(200, {"ok": True, "updatedAt": now})

        if route == "/api/teams/join":
            email = self.email_for_token()
            if not email:
                return self.send_json(401, {"error": "Sign in required"})
            code = str(body.get("inviteCode", "")).strip().upper()
            if not re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", code):
                return self.send_json(400, {"error": "Enter a valid 8-character team invite code"})
            with connect() as db:
                team = db.execute("SELECT id,name FROM teams WHERE invite_code=?", (code,)).fetchone()
                profile = db.execute("SELECT role FROM accounts WHERE email=?", (email,)).fetchone()
                if not team:
                    return self.send_json(404, {"error": "That team invite code was not found"})
                member_role = "player" if profile and profile[0] == "player" else "manager"
                db.execute("INSERT INTO team_members(team_id,email,role,player_id,joined_at) VALUES(?,?,?,?,?) "
                           "ON CONFLICT(team_id,email) DO NOTHING",
                           (team[0],email,member_role,str(body.get("playerId", "")),utc_now()))
                member = db.execute("SELECT role,player_id FROM team_members WHERE team_id=? AND email=?", (team[0],email)).fetchone()
            return self.send_json(200, {"id": team[0], "name": team[1], "role": member[0], "playerId": member[1]})

        if route == "/api/teams/rotate-invite":
            email = self.email_for_token()
            if not email:
                return self.send_json(401, {"error": "Sign in required"})
            team_id = str(body.get("teamId", ""))
            with connect() as db:
                owner = db.execute("SELECT 1 FROM teams WHERE id=? AND owner_email=?", (team_id,email)).fetchone()
                if not owner:
                    return self.send_json(403, {"error": "Only the team owner can change its invite code"})
                code = new_invite_code(db)
                db.execute("UPDATE teams SET invite_code=?,revision=revision+1,updated_at=? WHERE id=?", (code,utc_now(),team_id))
            return self.send_json(200, {"inviteCode": code})

        if route == "/api/logout":
            auth = self.headers.get("Authorization", "")
            token = auth[7:] if auth.startswith("Bearer ") else ""
            with connect() as db:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
            return self.send_json(200, {"ok": True})
        return self.send_json(404, {"error": "Not found"})


if __name__ == "__main__":
    migrate_legacy_database()
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    args = parser.parse_args()
    connect().close()
    print(f"Touchline SQLite account database: {DB}")
    print(f"Touchline server listening on http://localhost:{args.port}")
    try:
        for ip in sorted(set(socket.gethostbyname_ex(socket.gethostname())[2])):
            if not ip.startswith(("127.", "169.254.")):
                print(f"Open this address on other devices on your Wi-Fi: http://{ip}:{args.port}")
    except Exception:
        pass
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()
