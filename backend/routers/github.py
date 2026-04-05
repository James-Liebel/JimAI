"""GitHub and git repository routes for local IDE workflows."""

from __future__ import annotations

import re
import subprocess
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from agent_space.paths import PROJECT_ROOT

router = APIRouter(prefix="/api/github", tags=["github"])

BRANCH_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")


class CommitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    files: list[str] = Field(default_factory=list)


class FileSelectionRequest(BaseModel):
    files: list[str] = Field(default_factory=list)
    all: bool = False


class CheckoutRequest(BaseModel):
    branch: str = Field(min_length=1, max_length=200)


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git command failed").strip()
        raise HTTPException(status_code=400, detail=detail)
    return (result.stdout or "").strip()


def _normalize_files(files: list[str]) -> list[str]:
    clean: list[str] = []
    for raw in files:
        path = str(raw or "").replace("\\", "/").strip()
        if not path:
            continue
        clean.append(path)
    return clean


def _validate_branch_name(branch: str) -> str:
    name = str(branch or "").strip()
    if not name or not BRANCH_RE.fullmatch(name) or name.startswith(".") or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid branch name.")
    return name


def _current_branch() -> str:
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip() or "HEAD"


def _origin_url() -> str:
    try:
        return _run_git(["config", "--get", "remote.origin.url"]).strip()
    except HTTPException:
        return ""


def _github_rest_auth_header(token: str) -> str:
    """Fine-grained PATs use Bearer; classic PATs use token."""
    t = (token or "").strip()
    if t.startswith("github_pat_"):
        return f"Bearer {t}"
    return f"token {t}"


@router.get("/remote-repos")
async def github_remote_repos(
    max_repos: int = Query(default=200, ge=1, le=500),
    x_github_token: str | None = Header(default=None),
) -> dict:
    """List repositories visible to the user (owner, collaborator, org) via GitHub REST API."""
    token = (x_github_token or "").strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="GitHub token required. Paste a personal access token in the Git panel (local browser storage).",
        )

    repos: list[dict] = []
    page = 1
    per_page = min(100, max_repos)
    auth = _github_rest_auth_header(token)
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": auth,
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        while len(repos) < max_repos:
            resp = await client.get(
                "https://api.github.com/user/repos",
                params={
                    "per_page": per_page,
                    "page": page,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
                headers=headers,
            )
            if resp.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="GitHub rejected this token. For classic PATs use repo scope; for fine-grained allow repository read.",
                )
            if resp.status_code != 200:
                detail = (resp.text or "GitHub API error").strip()[:800]
                raise HTTPException(status_code=502, detail=detail)

            try:
                batch = resp.json()
            except Exception as exc:
                raise HTTPException(status_code=502, detail="Invalid JSON from GitHub API.") from exc

            if not isinstance(batch, list) or not batch:
                break

            for row in batch:
                if len(repos) >= max_repos:
                    break
                if not isinstance(row, dict):
                    continue
                clone_url = str(row.get("clone_url") or "").strip()
                if not clone_url:
                    continue
                repos.append({
                    "id": row.get("id"),
                    "name": str(row.get("name") or ""),
                    "full_name": str(row.get("full_name") or ""),
                    "clone_url": clone_url,
                    "description": row.get("description"),
                    "private": bool(row.get("private")),
                    "updated_at": str(row.get("updated_at") or ""),
                    "default_branch": str(row.get("default_branch") or "main"),
                })

            if len(batch) < per_page:
                break
            page += 1

    return {"repos": repos, "count": len(repos)}


def _auth_url(origin_url: str, token: str) -> str:
    if not token or not origin_url.startswith("https://github.com/"):
        return origin_url
    safe_token = quote(token, safe="")
    return origin_url.replace("https://", f"https://x-access-token:{safe_token}@")


def _has_staged_changes() -> bool:
    return bool(_run_git(["diff", "--cached", "--name-only"]).strip())


def _git_status_payload(token: str = "") -> dict:
    lines = _run_git(["status", "--porcelain=1", "-b"]).splitlines()
    branch_line = lines[0] if lines else "## HEAD"
    match = re.match(r"##\s+([^\s.]+)(?:\.\.\.([^\s]+))?(?:\s+\[(.*?)\])?", branch_line)
    branch = match.group(1) if match else "HEAD"
    upstream = match.group(2) if match else ""
    ahead = 0
    behind = 0
    detail = match.group(3) if match and match.group(3) else ""
    if detail:
        for part in detail.split(","):
            item = part.strip()
            if item.startswith("ahead "):
                ahead = int(item.replace("ahead ", "") or 0)
            if item.startswith("behind "):
                behind = int(item.replace("behind ", "") or 0)
    changes = []
    for raw in lines[1:]:
        if len(raw) < 4:
            continue
        index_status = raw[0]
        worktree_status = raw[1]
        path = raw[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        changes.append({
            "path": path.replace("\\", "/"),
            "index_status": index_status,
            "worktree_status": worktree_status,
            "staged": index_status not in {" ", "?"},
            "untracked": raw.startswith("??"),
        })
    return {
        "branch": branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "origin_url": _origin_url(),
        "token_configured": bool(token),
        "changes": changes,
    }


def _git_branch_payload() -> dict:
    current = _current_branch()
    local_names = {
        row.strip()
        for row in _run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads"]).splitlines()
        if row.strip()
    }
    remote_names = {
        row.strip().removeprefix("origin/")
        for row in _run_git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"]).splitlines()
        if row.strip() and row.strip() != "origin/HEAD"
    }
    branches = [
        {
            "name": name,
            "current": name == current,
            "local": name in local_names,
            "remote": name in remote_names,
        }
        for name in sorted(local_names | remote_names)
    ]
    return {"current": current, "branches": branches}


@router.get("/status")
async def github_status(x_github_token: str | None = Header(default=None)) -> dict:
    return _git_status_payload(token=(x_github_token or "").strip())


@router.get("/branches")
async def github_branches() -> dict:
    return _git_branch_payload()


@router.get("/log")
async def github_log() -> dict:
    rows = _run_git(["log", "-10", "--date=iso", "--pretty=format:%H%x1f%h%x1f%ad%x1f%an%x1f%s"]).splitlines()
    commits = []
    for row in rows:
        parts = row.split("\x1f")
        if len(parts) != 5:
            continue
        commits.append({
            "hash": parts[0],
            "short_hash": parts[1],
            "date": parts[2],
            "author": parts[3],
            "message": parts[4],
        })
    return {"commits": commits}


@router.post("/stage")
async def github_stage(req: FileSelectionRequest, x_github_token: str | None = Header(default=None)) -> dict:
    files = _normalize_files(req.files)
    if req.all or not files:
        _run_git(["add", "-A"])
    else:
        _run_git(["add", "--", *files])
    return {"ok": True, "status": _git_status_payload(token=(x_github_token or "").strip())}


@router.post("/unstage")
async def github_unstage(req: FileSelectionRequest, x_github_token: str | None = Header(default=None)) -> dict:
    files = _normalize_files(req.files)
    if req.all or not files:
        _run_git(["reset", "HEAD", "--", "."])
    else:
        _run_git(["reset", "HEAD", "--", *files])
    return {"ok": True, "status": _git_status_payload(token=(x_github_token or "").strip())}


@router.post("/checkout")
async def github_checkout(req: CheckoutRequest, x_github_token: str | None = Header(default=None)) -> dict:
    branch = _validate_branch_name(req.branch)
    if branch == _current_branch():
        return {"ok": True, "branch": branch, "output": "Already on requested branch.", "status": _git_status_payload(token=(x_github_token or "").strip()), "branches": _git_branch_payload()}
    local_exists = bool(_run_git(["branch", "--list", branch]).strip())
    remote_exists = bool(_run_git(["branch", "-r", "--list", f"origin/{branch}"]).strip())
    if local_exists:
        output = _run_git(["checkout", branch])
    elif remote_exists:
        output = _run_git(["checkout", "-b", branch, "--track", f"origin/{branch}"])
    else:
        output = _run_git(["checkout", "-b", branch])
    token = (x_github_token or "").strip()
    return {
        "ok": True,
        "branch": _current_branch(),
        "output": output,
        "status": _git_status_payload(token=token),
        "branches": _git_branch_payload(),
    }


@router.post("/commit")
async def github_commit(req: CommitRequest, x_github_token: str | None = Header(default=None)) -> dict:
    files = _normalize_files(req.files)
    if files:
        _run_git(["add", "--", *files])
    if not _has_staged_changes():
        raise HTTPException(status_code=400, detail="No staged changes to commit.")
    commit_output = _run_git(["commit", "-m", req.message.strip()])
    commit_hash = _run_git(["rev-parse", "HEAD"]).strip()
    token = (x_github_token or "").strip()
    return {
        "ok": True,
        "commit": {
            "hash": commit_hash,
            "message": req.message.strip(),
            "output": commit_output,
        },
        "status": _git_status_payload(token=token),
        "branches": _git_branch_payload(),
    }


@router.post("/push")
async def github_push(x_github_token: str | None = Header(default=None)) -> dict:
    branch = _current_branch()
    token = (x_github_token or "").strip()
    origin_url = _origin_url()
    auth_url = _auth_url(origin_url, token)
    output = _run_git(["push", auth_url, f"HEAD:refs/heads/{branch}"] if auth_url and token else ["push"])
    return {"ok": True, "output": output, "status": _git_status_payload(token=token), "branches": _git_branch_payload()}


@router.post("/pull")
async def github_pull(x_github_token: str | None = Header(default=None)) -> dict:
    branch = _current_branch()
    token = (x_github_token or "").strip()
    origin_url = _origin_url()
    auth_url = _auth_url(origin_url, token)
    output = _run_git(["pull", "--ff-only", auth_url, branch] if auth_url and token else ["pull", "--ff-only"])
    return {"ok": True, "output": output, "status": _git_status_payload(token=token), "branches": _git_branch_payload()}
