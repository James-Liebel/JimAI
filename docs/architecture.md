# Private AI System Architecture

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACES                         │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│   Frontend   │   Chrome     │   VS Code    │   CLI Scripts     │
│   (React)    │   Extension  │   Extension  │   (Python)        │
│   :5173      │   MV3        │   TypeScript │                   │
└──────┬───────┴──────┬───────┴──────┬───────┴────────┬──────────┘
       │              │              │                │
       └──────────────┴──────────────┴────────────────┘
                              │
                     HTTP / SSE (port 8000)
                              │
       ┌──────────────────────┴──────────────────────┐
       │              FASTAPI BACKEND                 │
       │                                              │
       │  ┌─────────┐  ┌─────────┐  ┌─────────────┐ │
       │  │ Chat API │  │Upload   │  │ Vision API  │ │
       │  │ /api/chat│  │/api/    │  │ /api/vision │ │
       │  │ (SSE)    │  │upload   │  │ (SSE)       │ │
       │  └────┬─────┘  └────┬────┘  └──────┬──────┘ │
       │       │              │              │        │
       │  ┌────┴──────────────┴──────────────┘        │
       │  │                                           │
       │  │  ┌──────────────────────────────────┐     │
       │  │  │         AGENT FRAMEWORK           │     │
       │  │  │  ┌────────────┐  ┌────────────┐  │     │
       │  │  │  │Orchestrator│  │ Math Agent  │  │     │
       │  │  │  │ (planner)  │  │ (SymPy)     │  │     │
       │  │  │  ├────────────┤  ├────────────┤  │     │
       │  │  │  │Code Agent  │  │Research Agt│  │     │
       │  │  │  │(exec+test) │  │(web search)│  │     │
       │  │  │  ├────────────┤  ├────────────┤  │     │
       │  │  │  │Writing Agt │  │            │  │     │
       │  │  │  │(style prof)│  │            │  │     │
       │  │  │  └────────────┘  └────────────┘  │     │
       │  │  └──────────────────────────────────┘     │
       │  │                                           │
       │  │  ┌──────────┐  ┌──────────┐              │
       │  │  │ ChromaDB │  │Knowledge │              │
       │  │  │(vectors) │  │Graph     │              │
       │  │  │chroma_db/│  │graph.json│              │
       │  │  └──────────┘  └──────────┘              │
       │  │                                           │
       └──┴───────────────────────────────────────────┘
                              │
                     HTTP (port 11434)
                              │
       ┌──────────────────────┴──────────────────────┐
       │                   OLLAMA                     │
       │                                              │
       │  BALANCED (default)        FAST              │
       │  ┌──────────────────┐  ┌──────────────────┐  │
       │  │deepseek-r1:14b   │  │qwen2-math:7b     │  │
       │  │(math/stats)      │  │(fast math)        │  │
       │  ├──────────────────┤  ├──────────────────┤  │
       │  │qwen2.5-coder:14b │  │qwen2.5-coder:7b  │  │
       │  │(code/data sci)   │  │(fast code + tabs) │  │
       │  ├──────────────────┤  └──────────────────┘  │
       │  │qwen3:8b          │                         │
       │  │(chat/reasoning)  │  DEEP (explicit only)  │
       │  ├──────────────────┤  ┌──────────────────┐  │
       │  │qwen2.5vl:7b      │  │qwen2.5:32b       │  │
       │  │(vision/OCR)      │  │(all roles, ~20GB) │  │
       │  ├──────────────────┤  └──────────────────┘  │
       │  │nomic-embed-text  │                         │
       │  │(embeddings)      │                         │
       │  └──────────────────┘                         │
       └──────────────────────────────────────────────┘
```

## Services and Ports

| Service  | Port  | Technology       | Description                    |
|----------|-------|------------------|--------------------------------|
| Backend  | 8000  | FastAPI (Python) | API server, agents, RAG        |
| Frontend | 5173  | Vite + React     | Chat UI with LaTeX/code render |
| Ollama   | 11434 | Ollama           | Local LLM inference            |

## Speed Modes

| Mode | Models | Speed | Use Case |
|------|--------|-------|----------|
| **Fast** | 7-8B variants | ~80 tok/s | Quick questions, tab completion, mobile |
| **Balanced** | 14B variants | ~45 tok/s | Default — good quality and speed |
| **Deep** | qwen2.5:32b | ~20 tok/s | Hard problems, explicit activation only |

Switch via: `POST /api/settings/speed-mode {"mode": "fast|balanced|deep"}`

## Model Routing Table (Balanced Mode)

| Role     | Model                    | Temperature | Purpose                          |
|----------|--------------------------|-------------|----------------------------------|
| math     | deepseek-r1:14b          | 0.1         | Math, statistics, LaTeX proofs   |
| code     | qwen2.5-coder:14b       | 0.05        | Code generation, debugging       |
| chat     | qwen3:8b                | 0.7         | General reasoning, discussion    |
| vision   | qwen2.5vl:7b            | 0.2         | Image analysis, OCR              |
| writing  | qwen3:8b                | 0.75        | Style-matched writing            |
| data     | qwen2.5-coder:14b       | 0.1         | Data science, EDA, ML            |
| embed    | nomic-embed-text        | 0.0         | Vector embeddings for RAG        |

Tab completion always uses `qwen2.5-coder:7b` regardless of speed mode.

## How RAG Works

1. **Ingestion**: Documents (PDF, DOCX, code, images) are uploaded via `/api/upload`
2. **Chunking**: Text is split into 512-char chunks with 64-char overlap
3. **Embedding**: Each chunk is embedded using `nomic-embed-text` via Ollama
4. **Storage**: Chunks + embeddings stored in ChromaDB (`chroma_db/`)
5. **Retrieval**: On each chat message, the query is embedded and top-5 similar chunks retrieved
6. **Augmentation**: Retrieved chunks are prepended to the prompt as context
7. **Sources**: Source metadata is returned to the frontend for the citations panel

## Agent Graph Flow

```
User Task
    │
    ▼
Orchestrator (qwen3:8b)
    │
    ├── Classify into subtasks
    │   Returns: [{task, agent, depends_on}]
    │
    ├── Execute subtasks (respecting dependencies)
    │   ├── Math Agent → deepseek-r1:14b + SymPy verification
    │   ├── Code Agent → qwen2.5-coder:14b + python_exec + test loop
    │   ├── Research Agent → web search + fetch + summarize + ingest
    │   └── Writing Agent → style profile + qwen3:8b
    │
    └── Synthesize all results into final response
```

## Fine-Tuning Pipeline

1. `scripts/build_corpus.py` — walks a document directory, extracts text, generates synthetic Q&A pairs
2. `scripts/finetune.py` — Unsloth LoRA fine-tuning on Mistral-7B with 4-bit quantization
3. `scripts/check_and_retrain.py` — monitors feedback count, triggers retraining at 200+ new entries

## Continuous Learning Loop

1. User gives feedback (thumbs up/down + notes + corrections) on assistant responses
2. Feedback stored in `data/feedback.jsonl`
3. `scripts/update_style_profile.py` analyzes approved text → updates `data/style_profile.json`
4. `scripts/check_and_retrain.py` monitors feedback count → triggers fine-tuning when threshold reached
5. Knowledge graph (`data/graph.json`) updated after each session with extracted entities

## Environment Variables

| Variable              | Default                  | Description                     |
|----------------------|--------------------------|----------------------------------|
| OLLAMA_BASE_URL      | http://localhost:11434   | Ollama server URL               |
| BACKEND_PORT         | 8000                     | FastAPI server port              |
| CHROMA_PATH          | ./chroma_db              | ChromaDB storage directory       |
| KNOWLEDGE_GRAPH_PATH | ./data/graph.json        | Knowledge graph file             |
| STYLE_PROFILE_PATH   | ./data/style_profile.json| Writing style profile            |
| LOG_LEVEL            | INFO                     | Logging level                    |
