@echo off
REM JimAI — single-command launcher.
REM
REM Starts: Ollama (if not already running), backend (FastAPI/uvicorn),
REM frontend (Vite dev), and the Electron desktop window. Closing the
REM Electron window terminates every process this launcher started.
REM
REM Usage: double-click this file, or run from any shell:
REM     "Start JimAI.cmd"

setlocal enableextensions
cd /d "%~dp0"

REM --- Sanity check: must be run inside the JimAI repo ----------------------
if not exist "desktop\main.cjs" (
    echo [JimAI] desktop\main.cjs not found. Run this from the repo root.
    pause
    exit /b 1
)
if not exist "backend\main.py" (
    echo [JimAI] backend\main.py not found. Run this from the repo root.
    pause
    exit /b 1
)

REM --- Resolve Python ------------------------------------------------------
set "PY=%~dp0backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

REM --- Resolve Node --------------------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
    echo [JimAI] node was not found on PATH. Install Node.js first.
    pause
    exit /b 1
)

REM --- Resolve Electron ----------------------------------------------------
REM Prefer the real electron.exe to dodge issues with .cmd shims under cmd
REM substitution. Fall back to the JS entry if the native binary is missing.
set "ELECTRON_EXE=%~dp0node_modules\electron\dist\electron.exe"
set "ELECTRON_CLI=%~dp0node_modules\electron\cli.js"
if not exist "%ELECTRON_EXE%" if not exist "%ELECTRON_CLI%" (
    echo [JimAI] Electron is missing. Running npm install once...
    pushd "%~dp0"
    call npm install --no-audit --no-fund
    popd
)
if not exist "%ELECTRON_EXE%" if not exist "%ELECTRON_CLI%" (
    echo [JimAI] Electron is still missing after npm install. Aborting.
    pause
    exit /b 1
)

REM --- Start Ollama in the background if not already running ---------------
REM Probe via tasklist; ollama serve is auto-started by the desktop app on
REM Windows, but if the user hasn't done that yet we kick it off here.
tasklist /FI "IMAGENAME eq ollama.exe" /FI "STATUS eq RUNNING" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    where ollama >nul 2>nul
    if not errorlevel 1 (
        echo [JimAI] starting ollama serve in background...
        start "ollama" /B ollama serve
    ) else (
        echo [JimAI] WARNING: ollama not on PATH; local-model features will be unavailable.
    )
)

REM --- Launch Electron with self-managed children ---------------------------
set "AGENTSPACE_PYTHON=%PY%"
set "JIMAI_MANAGE_SERVICES=1"
set "AGENTSPACE_AUTO_STOP=0"
set "JIMAI_BACKEND_PORT=8000"
set "JIMAI_FRONTEND_PORT=5173"
set "AGENTSPACE_UI_URL=http://127.0.0.1:5173"

echo [JimAI] launching desktop app...
if exist "%ELECTRON_EXE%" (
    "%ELECTRON_EXE%" "%~dp0desktop\main.cjs"
) else (
    node "%ELECTRON_CLI%" "%~dp0desktop\main.cjs"
)
set "EC=%ERRORLEVEL%"

echo [JimAI] desktop window closed (exit code %EC%); managed services were terminated.
exit /b %EC%
