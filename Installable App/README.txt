TOUCHLINE — INSTALLABLE LOCAL FOOTBALL APP

START
1. Extract this folder from Touchline-App.zip.
2. Double-click "Start Touchline.bat". Python 3 must be installed.
3. The app opens at http://localhost:8765/index.html. The server also prints a local network address for other devices on the same Wi-Fi.
4. In Chrome or Edge, choose the install icon in the address bar, or open the browser menu and choose Install Touchline.
5. Keep the minimized "Touchline Server" window open while using the installed app. Close it to stop the local app server.

WHAT'S INSIDE
- Team setup, kits, format selection, availability, squad, and lineup screens.

- Formation library for 5-a-side, 7-a-side, 9-a-side, and 11-a-side, with separate pitch rows for multi-line shapes.
- Live score, running clock, kick-off/pause/resume, half-time and full-time controls, and a scrollable live lineup with goals, assists, and card markers. Remove a recorded event to reverse the score and player stats.
- Match history, season leaderboards, and personal player cards using the same squad statistics. Managers can browse every card; player card share links include a portable stats snapshot.
- Any home/away color via color picker or hex value; nine kit patterns and selectable number fonts; upload, crop, reshape, or remove a transparent club crest; set the opposing team and captain; and customize the lineup.
- Downloadable Instagram post and story graphics for the starting XI and matchday poster, with an in-app image preview before saving.
- Offline app shell and local browser storage for this demo.

Choose a manager or player role when creating an account; player accounts can link to a squad profile now or later. Accounts use a local SQLite database on the host computer. Passwords are salted PBKDF2 hashes, sessions expire after 30 days, and account snapshots use version checks. Teams, memberships, player records, fixtures, matches and match events are also stored as queryable SQLite records. A manager can share a club from Settings → Club access; after the first sync, refresh to see its invite code. Players and other managers can join with that code and open the shared team from the same section. Team data is available only to signed-in members. Keep Touchline Server running; devices on the same Wi-Fi use the printed host address. The database file is outside the web app folder and is not served to browsers. This is a self-hosted local-network app, not yet a public internet cloud service; public access requires hosting, HTTPS, backups and operational monitoring. Portable JSON backup/import is available.

LATEST LINEUP & IMAGE FEATURES
- Use the Lineup screen from the main navigation, or open it from Match Centre and Squad.
- Drag a jersey to position it; drag a substitute onto the pitch to start them, or drag a starter to the bench.
- Tap or keyboard-select a starter jersey to choose a substitute from the bench; the replacement keeps that field position.
- Choose a cover player and upload a portrait from the Lineup screen for the editorial PNG.
- Crop club crests with zoom and horizontal/vertical framing, then save them as a shield, circle, or square.
- Add up to four transparent PNG, WebP, or SVG poster overlays; choose a corner for each, then remove them individually when needed.
- Switch between 2D tactical and shaded 3D pitch views. The editorial lineup poster is a separate portrait and roster design.
- Switch between home and away kits on the Lineup screen; the selected kit is also used in the exported team sheet preview.
- The lineup pitch shows player jerseys, names, positions, captain badge, club crest, and a separate substitutes list.
- Edit home and away kit pattern, trim, and number colors in Club setup. The supplied transparent single-shirt template is used in kit previews and on the lineup; home/away colors, trim, and number colors recolor the shirt while preserving its outline.
- Every exported image opens in a preview first. Preview and download lineup sheets, final score graphics, player of the match graphics, and player cards.
- Open any history row to see its full match-centre timeline, lineup, and ratings.












FIXTURES, SETTINGS & ACCOUNTS
- Open Fixtures to add upcoming games with opponent, kick-off date/time, venue, format, and player gear notes. Start that fixture from its card to load it into Match Centre.
- Open Settings for light/dark appearance, account sync, multiple teams, and portable backups.
- Run Touchline Server on one computer. On another device on the same Wi-Fi, open the local network address printed by the server, then sign into the same account.
- Remove players from Squad while preserving their completed match records. Edit the manager name from the Lineup manager panel.
- Preview the selected starting XI on the formation pitch separately from the downloadable team sheet poster. The poster uses the club crest over a soft club-color gradient.
- Players can have up to three preferred positions in Squad. Managers can build an XI from scratch, then tap formation spots to assign players.
- Post-match ratings accept whole numbers and decimals from 1.0 to 10.0.
- The live clock updates continuously while the match runs and freezes when paused. Use Half time to pause for the break, then Resume to start the second half; the Player of the Match action appears after full time. Record either team’s goals and other match events, and remove a disallowed event to adjust the score and stats. Formation spots suggest squad players with matching preferred positions. Kit preview numbers are larger and easier to read, and each kit can use a different number font.


SHARED CLUBS
- Create a manager or player account in Settings. A player can join without a local player profile, then use Club access to join with the team invite code.
- Managers share the invite code with trusted team members. Joined members can open the club and see its current squad, fixtures, lineup, statistics and match records.
- Account and team data are saved to the SQLite database on the computer running Touchline Server. Keep that computer online for other devices.
- Sign-in and shared team access work on the host or local Wi-Fi. A public launch still needs a hosted database, HTTPS, account recovery, email verification and production operations.

PUBLISH TO THE INTERNET
See PUBLISHING.md for the Render deployment steps. If uploading the whole project repository, use render.yaml at the repository root. If uploading this Installable App folder as the repository, use the included render.yaml.

