@echo off
cd /d "%~dp0.."
set "PY=backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" scripts\agentspace_lifecycle.py free-stack-install-runtime --runtime docker %*
