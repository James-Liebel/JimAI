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

REM Same click again: stops backend, frontend, and desktop when both are up.
"%PY%" scripts\agentspace_lifecycle.py toggle
if errorlevel 1 (
  echo.
  echo Something went wrong. Read the messages above.
  pause
  exit /b 1
)

exit /b 0
