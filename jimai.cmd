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
if /I "%~1"=="force" goto force
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
"%PY%" scripts\agentspace_lifecycle.py desktop --with-services
if errorlevel 1 goto fail
echo.
echo If no JimAI window appeared: run   npm install   in this folder, then try jimai again.
exit /b 0

:force
cd /d "%PROJECT_DIR%"
echo Starting JimAI with port cleanup (--free-ports^)...
echo Using Python: "%PY%"
echo.
"%PY%" scripts\agentspace_lifecycle.py desktop --with-services --free-ports
if errorlevel 1 goto fail
echo.
echo If no JimAI window appeared: run   npm install   in this folder, then try jimai again.
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
echo   jimai         Start JimAI desktop and required local services
echo   jimai force   Same, but free backend port 8000 if something stuck is listening
echo   jimai stop    Stop JimAI and listeners on its usual ports
echo   jimai open    Focus or start the JimAI desktop app
echo   jimai browser Open the browser UI and start local services if needed
exit /b 0

:fail
set "JIMEC=%ERRORLEVEL%"
echo.
echo JimAI exited with an error (code %JIMEC%^).
echo Run jimai.cmd from an already-open CMD window to see full output, or read the messages above.
pause
exit /b %JIMEC%
