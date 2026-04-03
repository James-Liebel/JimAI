## Security Review

Date: 2026-03-17
Scope: `private-ai` repository publish-readiness review for local-only usage and public source visibility.

### Summary

- No tracked hardcoded API keys or private keys were found in the repository files reviewed.
- The repository already ignores major sensitive/local-only paths such as `.env`, `data/agent_space/`, model files, virtual environments, and local databases.
- Three publish-hygiene issues were identified and fixed:
  - accidental `%USERPROFILE%` npm-cache folders inside the repo tree were not ignored
  - backend auth scaffolding contained unused code that could auto-write a generated API key into `.env`
  - a workflow template contained a hardcoded absolute local repo path with the Windows username embedded

### Findings

#### Fixed

1. Accidental cache and temp artifacts could be published
- Risk: medium
- Fix:
  - added ignore rules for:
    - `%USERPROFILE%/`
    - `frontend/%USERPROFILE%/`
    - `backend/tests/_tmp_*`
    - `backend/tmp_*.txt`
    - `err.txt`

2. Backend contained secret-sprawl behavior
- Risk: medium
- File: `backend/main.py`
- Issue:
  - an unused helper function could generate an API key and append it into `.env`
- Fix:
  - removed the unused auto-write helper
  - repository no longer contains code that silently persists a generated auth secret during runtime startup

3. Backend contained a hardcoded local path
- Risk: low
- File: `backend/agent_space/api.py`
- Issue:
  - a workflow template embedded `c:/Users/...` in a git command, exposing the local Windows username in the public repo
- Fix:
  - replaced the hardcoded path with a repo-relative `git status --porcelain` command

#### Remaining publish considerations

1. This project is configured primarily for local use
- `PRIVATE_AI_AUTH_REQUIRED` defaults to `false`
- this is acceptable for local-only development, but should not be exposed directly to the internet without enabling auth

2. Localhost and local-network assumptions are intentional
- multiple configs and extensions target `localhost`
- this is not a security bug by itself; it matches the local-first product design

3. Large dirty worktree
- the repository contains many local edits and untracked files
- before public publication, only the intended showcase state should be committed

### Public Repo Recommendation

Safe to publish if you:

- do not commit `.env`
- do not commit runtime data under `data/agent_space/`
- do not commit local secret exports such as free-stack credential bundles
- do not commit local caches, logs, or generated `%USERPROFILE%` npm-cache folders
- verify there are no personal credentials inside any still-untracked local files before commit

### Operational Recommendation

For a public showcase repo:

- keep the source public
- keep real runtime secrets only in local `.env`
- describe the app as local-first in the README
- do not expose the backend publicly unless API auth is enabled and access is intentionally controlled
