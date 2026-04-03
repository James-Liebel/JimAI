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

REM Always start or reuse backend + frontend + desktop (same as jimai.cmd).
REM Use: jimai stop   or   jimai toggle   from CMD if you want to stop the stack.
"%PY%" scripts\agentspace_lifecycle.py desktop --with-services --free-ports
if errorlevel 1 (
  echo.
  echo Something went wrong. Read the messages above.
  pause
  exit /b 1
)

exit /b 0
