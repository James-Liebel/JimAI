# Agent skills (`skills/`)

Skill files are Markdown (`.md`) documents that teach an agent **how** to perform a capability: checklists, frameworks, decision rules, and short examples. They are **not** the agent’s core persona—that lives in the agent’s **system prompt** in the Agents UI.

## Layout

```
skills/
  README.md           ← this file
  shared/             ← optional skills injected for whole teams
  <agent-slug>/       ← one directory per agent (matches agent `slug`)
    my-skill.md
```

At run time, the backend loads every `*.md` in `skills/<agent-slug>/`, wraps each file in a `<skill>` block, and appends them inside `<available_skills>` on top of the agent’s system prompt.

## Creating skills

1. **UI (recommended)**  
   In **Build → Agents**, select an agent → **Skills** panel → **Generate skill**. After preview, save to write `skills/<slug>/<skill-slug>.md`.

2. **Manually**  
   Add `skills/<agent-slug>/<name>.md`. Use clear headings and second person (“You should…”). Keep one main capability per file.

3. **Script**  
   `python scripts/generate_default_skills.py` generates a default set via the local Ollama model (see script help).

## Team shared skills

Teams can list **shared** skill paths (usually under `shared/`) that are injected for every member on a team run.

## Best practices

- One skill = one capability (e.g. “code review”, not “everything about Python”).
- Prefer checklists and “if X then Y” rules over vague advice.
- Include 1–2 short good vs bad examples where it helps.
- Keep roughly **300–600 words** unless the task truly needs more.

## Validation

```bash
python scripts/validate_skills.py
python scripts/list_skills.py
```
