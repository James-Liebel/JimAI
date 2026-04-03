# JimAI-1 — App Structure Overview

A local-first AI assistant platform. Runs a Python backend, React frontend, and optional desktop/extension clients. All AI inference goes through local Ollama models by default.

---

## Top-Level Layout

```
JimAI-1/
├── backend/        Python FastAPI server — all AI logic, agents, tools, APIs
├── frontend/       React + Vite SPA — main user interface
├── desktop/        Electron wrapper for desktop app
├── extension/      Browser extension (sidebar)
├── vscode-ext/     VS Code extension
├── infra/          Docker/Podman free-stack deployment config
├── scripts/        Dev, build, start/stop, and maintenance scripts
├── skills/         Claude Code skill definitions (.md)
├── data/           Persistent app data (sessions, memory, etc.)
├── docs/           Additional documentation
└── jimai.cmd       Windows root launcher
```

---

## Backend (`backend/`)

FastAPI Python server. Entry point: `main.py`.

| Layer | Purpose |
|---|---|
| `api/` | HTTP route handlers — chat, completion, agents, settings, teams, vision, feedback, upload, webtools, system agent |
| `routers/` | Additional routers — GitHub integration, agent workspace |
| `agents/` | Agent implementations — orchestrator, code, research, math, data, writing, builder, judge, self-consistency, graph planner, system agent |
| `tools/` | Callable tools agents use — web search, Python exec, file I/O, git, math, notebook, screenshot, test runner, LaTeX render |
| `models/` | Ollama client wrapper, prompt templates, model router (decides which local model to use) |
| `memory/` | Session and long-term memory storage |
| `config/` | App configuration |
| `agent_space/` | Isolated execution sandbox for agent workspaces |

---

## Frontend (`frontend/`)

React 18 + TypeScript + Vite + Tailwind. Entry: `src/main.tsx`.

| Layer | Purpose |
|---|---|
| `src/pages/` | Top-level views — Chat, Dashboard, Research, Builder, Notebook, Agents, AgentStudio, Automation, Settings, SelfCode, SystemAudit, SystemPanel, WorkflowReview |
| `src/components/` | Shared UI — ChatThread, InputBar, MessageBubble, SessionSidebar, AgentStatus, ModeSelector, GitHubPanel, FileUpload, LatexRenderer, MobileNav, RouterBadge, SpeedModeToggle, AppLayout, ErrorBoundary |
| `src/hooks/` | Custom React hooks |
| `src/lib/` | Utility functions and API client helpers |

---

## Desktop (`desktop/`)

Electron app (`main.cjs`) that wraps the frontend in a native window. Reads from `icons/` for app icons.

---

## Extension (`extension/`)

Browser extension. Sidebar UI in `sidebar/`, content scripts in `src/`. Webpack bundled.

---

## Infra (`infra/free-stack/`)

Docker Compose / Podman config for a self-contained deployment. Used by the `agent-space-free-*` scripts.

---

## Scripts (`scripts/`)

Utility scripts for lifecycle management, training, and setup:
- `start.sh / start.ps1 / stop.ps1` — start/stop the full stack
- `agentspace_lifecycle.py` — programmatic start/stop of agent workspace
- `finetune.py / check_and_retrain.py / build_corpus.py` — local fine-tuning pipeline
- `generate_default_skills.py / validate_skills.py` — skill management
- `repo_audit_static.py / run_all_phases_validation.py` — audit and validation tooling
- `setup_autostart.ps1 / setup_power_settings.ps1 / keep_alive.ps1` — Windows service setup

---

## Data Flow (simplified)

```
User (browser/desktop/extension)
  → frontend (React SPA)
    → backend API (FastAPI)
      → model router (selects local Ollama model)
        → agent / tool execution
          → response streamed back to UI
```

---

## Key Design Decisions

- **Local-first**: All inference via Ollama, no cloud AI required by default.
- **Multi-client**: Same backend serves the web UI, Electron desktop app, browser extension, and VS Code extension.
- **Agent architecture**: Orchestrator delegates to specialized sub-agents (code, research, math, etc.) and tools.
- **Agent workspace**: Isolated sandboxed environment for untrusted agent code execution.
