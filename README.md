# JimAI

JimAI is a local-first AI workspace for building apps, running autonomous agent workflows, reviewing code changes, researching on the web, and improving the system itself.

The stack is designed to run primarily on your own machine:
- local models through Ollama
- FastAPI backend
- React/Vite frontend
- Electron desktop shell
- optional local infra services for search, vector storage, dashboards, and automation

## What It Does

- Multi-agent runs with planner/verifier flows, team definitions, and review-gated changes
- Local app-building workspace with Builder, Agent Studio, Workflow Review, and SelfCode flows
- Web-backed Chat and Research with source visibility and live/fresh-data handling
- Browser automation through Playwright-backed sessions
- Automation/workflow graph support with local-first execution and optional n8n compatibility
- Snapshot, undo, rollback, export, and run-summary support
- Skills-based orchestration with markdown `SKILL.md` instructions

## Core Surfaces

| Surface | Default URL / Port | Purpose |
|---|---|---|
| Frontend | `http://localhost:5173` | Main UI for chat, build, review, automation, settings |
| Backend | `http://localhost:8000` | API, orchestration, review, research, browser, power controls |
| Ollama | `http://localhost:11434` | Local model runtime |
| Desktop | local Electron shell | Desktop wrapper around the main UI |

## Main Product Areas

- `Dashboard`: health, status, recent runs
- `Builder`: app-building prompt flow and autonomous execution
- `Workflow Review`: diff review, apply, undo, rollback
- `Chat`: local chat with optional live web lookup for current-data prompts
- `Research`: multi-source search, source reading, grounded synthesis
- `SelfCode`: self-improvement runs against the repo
- `Automation`: local workflow builder and optional n8n-compatible flows
- `Agent Studio`: team setup, skills, orchestration
- `Settings`: runtime, policy, and integration controls

## Quick Start

### 1. Start Ollama and pull the required models

```powershell
ollama pull qwen3:8b
ollama pull qwen2.5-coder:14b
ollama pull deepseek-r1:14b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text
```

### 2. Install dependencies

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

cd ..\frontend
npm install
```

### 3. Run the app

```powershell
cd ..\backend
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000

cd ..\frontend
npm run dev
```

Then open `http://localhost:5173`.

## Lifecycle Scripts

The repo includes helper scripts for local startup, desktop launch, and free-stack services.

```powershell
python scripts/agentspace_lifecycle.py start --open
python scripts/agentspace_lifecycle.py stop
python scripts/agentspace_lifecycle.py desktop --with-services
python scripts/agentspace_lifecycle.py free-stack-start --open
python scripts/agentspace_lifecycle.py free-stack-stop
```

## Testing

### Frontend

```powershell
cd frontend
npm test
npm run build
```

### Backend / validation

```powershell
python scripts/run_all_phases_validation.py
```

## Security Notes

- This project is intended to run locally by default.
- Keep `.env` local. Do not commit live credentials, tokens, or generated secret files.
- Local runtime data, chat history, logs, snapshots, exports, and secret files are not meant for source control.
- The public repo intentionally excludes most runtime state. Skills content is retained because it is part of the product behavior.
- If you expose the backend beyond localhost, review authentication, CSRF, rate limiting, and secret management first.

See [SECURITY_REVIEW.md](SECURITY_REVIEW.md) for the latest repo-level review summary.

## Repository Layout

```text
backend/    FastAPI app, orchestration, research, browser, review logic
frontend/   React/Vite UI
desktop/    Electron shell
docs/       audits, architecture notes, capability snapshots
scripts/    lifecycle, validation, and local helper scripts
infra/      local stack and service definitions
```

## Current Status

This repo is an active local product workspace, not a frozen template. The public version is meant to show the system architecture, UI, orchestration, and engineering work while keeping machine-specific runtime state out of Git.
