@echo off
setlocal
cd /d "%~dp0\.."
set APP_ENV=pro
set LOG_LEVEL=INFO
echo [live-crawler refresh-tiktok-credentials] APP_ENV=%APP_ENV%, LOG_LEVEL=%LOG_LEVEL%
echo Working directory: %CD%
echo.

python -m jobs.refresh_tiktok_credentials

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] refresh-tiktok-credentials exited with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo.
echo [SUCCESS] refresh-tiktok-credentials completed
endlocal