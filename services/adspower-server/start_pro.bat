@echo off
setlocal
cd /d "%~dp0"
set APP_ENV=pro
echo [adspower-server] APP_ENV=%APP_ENV%
python -m app.main
pause
endlocal
