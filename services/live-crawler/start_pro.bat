@echo off
setlocal
cd /d "%~dp0"
set APP_ENV=pro
set LOG_LEVEL=INFO
echo [live_dp] APP_ENV=%APP_ENV%, LOG_LEVEL=%LOG_LEVEL%
python main.py --mode scheduler
pause
endlocal
