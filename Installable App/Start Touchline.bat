@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "Touchline Server" /min py -3 server.py --bind 0.0.0.0 --port 8765
  timeout /t 2 /nobreak >nul
  start "" http://localhost:8765/index.html
  exit /b
)
where python >nul 2>nul
if %errorlevel%==0 (
  start "Touchline Server" /min python server.py --bind 0.0.0.0 --port 8765
  timeout /t 2 /nobreak >nul
  start "" http://localhost:8765/index.html
  exit /b
)
echo Python 3 was not found. Install Python 3, then run this file again.
pause
