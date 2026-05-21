@echo off
setlocal
cd /d "%~dp0"
set APP_ENV=pro
set PYTHONUNBUFFERED=1
echo [adspower-server] APP_ENV=%APP_ENV%
python -m app.main
pause
endlocal
