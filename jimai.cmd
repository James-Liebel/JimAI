@echo off
setlocal
cd /d "%~dp0"

if not exist "scripts\agentspace_lifecycle.py" (
  echo JimAI project files were not found next to this script. Expected scripts\agentspace_lifecycle.py
  echo.
  pause
  exit /b 1
)

set "PROJECT_DIR=%~dp0"
set "PY=%PROJECT_DIR%backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if /I "%~1"=="stop" goto stop
if /I "%~1"=="toggle" goto toggle
if /I "%~1"=="force" goto app
if /I "%~1"=="restart" goto restart
if /I "%~1"=="open" goto app
if /I "%~1"=="browser" goto browser
if /I "%~1"=="help" goto help
if /I "%~1"=="--help" goto help
if /I "%~1"=="-h" goto help

:app
cd /d "%PROJECT_DIR%"
echo Starting JimAI (desktop + services^)...
echo Using Python: "%PY%"
echo.
"%PY%" scripts\agentspace_lifecycle.py desktop --with-services --free-ports
if errorlevel 1 goto fail
echo.
echo If no JimAI window appeared: run   npm install   in this folder, then try jimai again.
exit /b 0

:restart
cd /d "%PROJECT_DIR%"
echo Stopping JimAI services, then starting again...
echo Using Python: "%PY%"
echo.
"%PY%" scripts\agentspace_lifecycle.py stop
"%PY%" scripts\agentspace_lifecycle.py desktop --with-services --free-ports
if errorlevel 1 goto fail
echo.
echo If no JimAI window appeared: run   npm install   in this folder, then try jimai again.
exit /b 0

:toggle
cd /d "%PROJECT_DIR%"
echo Using Python: "%PY%"
echo.
"%PY%" scripts\agentspace_lifecycle.py toggle
if errorlevel 1 goto fail
exit /b 0

:stop
cd /d "%PROJECT_DIR%"
"%PY%" scripts\agentspace_lifecycle.py stop
if errorlevel 1 goto fail
exit /b 0

:browser
cd /d "%PROJECT_DIR%"
"%PY%" scripts\agentspace_lifecycle.py open-ui
if errorlevel 1 goto fail
exit /b 0

:help
echo Usage:
echo   Open JimAI.cmd   Double-click: start or stop the stack
echo   jimai            Start desktop + backend + frontend
echo   jimai toggle     Same as Open JimAI.cmd
echo   jimai stop       Stop services and listeners
echo   jimai restart    Stop then start
echo   jimai browser    Open UI in browser ^(starts services if needed^)
exit /b 0

:fail
set "JIMEC=%ERRORLEVEL%"
echo.
echo JimAI exited with an error (code %JIMEC%^).
echo Run jimai.cmd from an already-open CMD window to see full output, or read the messages above.
pause
exit /b %JIMEC%
