@echo off
setlocal
cd /d "%~dp0"

if not exist "scripts\agentspace_lifecycle.py" (
  echo JimAI project files were not found next to this script.
  pause
  exit /b 1
)

set "PROJECT_DIR=%~dp0"
set "PY=%PROJECT_DIR%backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if /I "%~1"=="stop"    goto stop
if /I "%~1"=="toggle"  goto toggle
if /I "%~1"=="restart" goto restart
if /I "%~1"=="open"    goto app
if /I "%~1"=="force"   goto app
if /I "%~1"=="browser" goto browser
if /I "%~1"=="help"    goto help
if /I "%~1"=="--help"  goto help
if /I "%~1"=="-h"      goto help

:app
echo Starting JimAI (desktop + services)...
"%PY%" scripts\agentspace_lifecycle.py desktop --with-services --free-ports
if errorlevel 1 goto fail
echo.
echo If no JimAI window appeared: run   npm install   in this folder, then try again.
exit /b 0

:restart
echo Stopping JimAI, then starting again...
"%PY%" scripts\agentspace_lifecycle.py stop
"%PY%" scripts\agentspace_lifecycle.py desktop --with-services --free-ports
if errorlevel 1 goto fail
exit /b 0

:toggle
"%PY%" scripts\agentspace_lifecycle.py toggle
if errorlevel 1 goto fail
exit /b 0

:stop
"%PY%" scripts\agentspace_lifecycle.py stop
if errorlevel 1 goto fail
exit /b 0

:browser
"%PY%" scripts\agentspace_lifecycle.py open-ui
if errorlevel 1 goto fail
exit /b 0

:help
echo Usage:
echo   Open JimAI.cmd           Double-click: start desktop + backend + frontend
echo   Open JimAI.cmd toggle    Stop if running, start if stopped
echo   Open JimAI.cmd stop      Stop all services
echo   Open JimAI.cmd restart   Stop then start
echo   Open JimAI.cmd browser   Open UI in browser (starts services if needed)
exit /b 0

:fail
set "EC=%ERRORLEVEL%"
echo.
echo JimAI exited with an error (code %EC%).
pause
exit /b %EC%
