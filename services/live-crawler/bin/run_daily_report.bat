@echo off
setlocal
cd /d "%~dp0\.."
set APP_ENV=pro
set LOG_LEVEL=INFO
echo [live-crawler daily-report] APP_ENV=%APP_ENV%, LOG_LEVEL=%LOG_LEVEL%
echo Working directory: %CD%
echo.

python -m scripts.daily_report

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] daily-report exited with code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [SUCCESS] daily-report completed
pause
endlocal
