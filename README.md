# JimAI

Single public repository: **https://github.com/James-Liebel/JimAI**

## Clone

```bash
git clone https://github.com/James-Liebel/JimAI.git
cd JimAI
```

## Windows quick start

- Install [Ollama](https://ollama.com/) and pull models you need.
- Create a Python venv under `backend\.venv` and install backend deps (see project docs).
- From this repo root, run **`jimai.cmd`** (or `jimai force` if port 8000 is stuck).

## Layout

- `backend/` — FastAPI app  
- `frontend/` — React UI  
- `desktop/` — Electron shell  
- `scripts/` — lifecycle, skills, dev helpers  
- `jimai.cmd` — Windows launcher at repo root  

There is no separate “wrapper” repo; everything lives here.
