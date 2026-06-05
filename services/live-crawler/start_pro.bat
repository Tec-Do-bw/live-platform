  @echo off
  setlocal
  cd /d "%~dp0"
  set APP_ENV=pro
  set LOG_LEVEL=INFO
  echo [live-crawler] APP_ENV=%APP_ENV%, LOG_LEVEL=%LOG_LEVEL%

  start "live-crawler scheduler" /D "%~dp0" cmd /k "set APP_ENV=pro&& set LOG_LEVEL=INFO&& python main.py --mode scheduler"
  start "live-crawler cookie-api" /D "%~dp0" cmd /k "set APP_ENV=pro&& set LOG_LEVEL=INFO&& python -m monitor.server"
  start "live-crawler lazada-cookie-keeper" /D "%~dp0" cmd /k "set APP_ENV=pro&& set LOG_LEVEL=INFO&& python -m cookie_keeper"
  start "live-crawler daily-report" /D "%~dp0" cmd /k "set APP_ENV=pro&& set LOG_LEVEL=INFO&& python -m scripts.daily_report"

  echo.
  echo Started 5 live-crawler service windows
  pause
  endlocal
