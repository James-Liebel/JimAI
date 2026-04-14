"""Web research pipeline with rewrite, multi-source search, deep fetch, streaming synthesis, and Qdrant cache."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from models import ollama_client
from tools import web_search as legacy_web_search

from .config import SettingsStore
from .paths import BACKEND_ROOT, DATA_ROOT, MEMORY_DIR, PROJECT_ROOT, ensure_layout

logger = logging.getLogger(__name__)

DDG_API = "https://api.duckduckgo.com/"
WIKI_API = "https://en.wikipedia.org/w/api.php"
BING_SEARCH_URL = "https://www.bing.com/search"
GOOGLE_SEARCH_URL = "https://www.google.com/search"
SEARCH_TTL = 15 * 60
FETCH_TTL = 30 * 60
CACHE_FILE = MEMORY_DIR / "web_research_cache.json"
COLLECTION = "search_memory"
CACHE_HIT_MIN = 0.88
QUERY_REWRITE_TIMEOUT_S = 20.0
EXACT_CACHE_TTL_SECONDS = 12 * 60 * 60
SERVICE_STATUS_CACHE_TTL_SECONDS = 30
PARALLEL_PROVIDER_TIMEOUT_S = 5.0
_settings = SettingsStore()
_exact_answer_cache: dict[str, dict[str, Any]] = {}
_service_status_cache_data: dict[str, Any] | None = None
_service_status_cache_ts: float = 0.0

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot)",
    "Accept-Language": "en-US,en;q=0.9",
}
FETCH_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SHOPPING_SIGNALS = (
    "price",
    "cost",
    "buy",
    "cheap",
    "best",
    "review",
    "vs",
    "$",
    "how much",
    "where to",
    "gloves",
    "shoes",
    "jersey",
    "bat",
    "ball",
    "gear",
    "equipment",
)
NEWS_SIGNALS = (
    "latest",
    "today",
    "breaking",
    "2025",
    "2026",
    "recently",
    "announce",
    "update",
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _perf_delta(started_at: float) -> float:
    return max(0.0, time.perf_counter() - float(started_at))


def _exact_query_key(query: str) -> str:
    return str(query or "").strip().lower()


def _format_age_label(ts_iso: str) -> str:
    raw = str(ts_iso or "").strip()
    if not raw:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - parsed
        seconds = max(0, int(delta.total_seconds()))
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 48:
            return f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"
    except Exception:
        return "unknown"


def _exact_cache_get(query: str) -> dict[str, Any] | None:
    key = _exact_query_key(query)
    if not key:
        return None
    row = _exact_answer_cache.get(key)
    if not isinstance(row, dict):
        return None
    age = time.time() - float(row.get("stored_at", 0.0))
    if age > EXACT_CACHE_TTL_SECONDS:
        _exact_answer_cache.pop(key, None)
        return None
    return dict(row)


def _exact_cache_put(query: str, answer: str, sources: list[dict[str, Any]], ts_iso: str | None = None) -> None:
    key = _exact_query_key(query)
    if not key or not str(answer or "").strip():
        return
    now_iso = ts_iso or _now_iso()
    _exact_answer_cache[key] = {
        "answer": str(answer or ""),
        "sources": list(sources or []),
        "ts": now_iso,
        "stored_at": time.time(),
    }


def _cache_key(kind: str, raw: str) -> str:
    return hashlib.sha256(f"{kind}:{str(raw).strip().lower()}".encode("utf-8")).hexdigest()


# In-memory disk-cache mirror: loaded once, kept hot, written through on puts.
_disk_cache_items: dict[str, Any] | None = None


def _load_cache() -> dict[str, Any]:
    global _disk_cache_items
    if _disk_cache_items is not None:
        return {"items": _disk_cache_items}
    ensure_layout()
    if not CACHE_FILE.exists():
        _disk_cache_items = {}
        return {"items": _disk_cache_items}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        _disk_cache_items = dict(data.get("items") or {})
    except Exception:
        _disk_cache_items = {}
    return {"items": _disk_cache_items}


def _cache_get(kind: str, raw: str, ttl: int) -> dict[str, Any] | None:
    row = dict(_load_cache().get("items", {})).get(_cache_key(kind, raw))
    if not isinstance(row, dict):
        return None
    age = int(max(0.0, time.time() - float(row.get("created_at") or 0.0)))
    if age > max(1, ttl):
        return None
    payload = dict(row.get("payload") or {})
    payload["cached"] = True
    payload["cache_age_seconds"] = age
    return payload


def _cache_put(kind: str, raw: str, payload: dict[str, Any]) -> None:
    global _disk_cache_items
    cache = _load_cache()
    items = dict(cache.get("items") or {})
    items[_cache_key(kind, raw)] = {"created_at": time.time(), "payload": dict(payload)}
    _disk_cache_items = items
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("web_research: cache write failed", exc_info=True)


def _searxng_url() -> str:
    # NOTE: SearXNG settings.yml is currently internal to the container
    # (not mounted in infra/free-stack/docker-compose.yml), so redirect
    # cleanup is enforced in code via resolve_bing_url().
    explicit = str(os.getenv("SEARXNG_BASE_URL", "") or os.getenv("AGENT_SPACE_SEARXNG_URL", "")).strip()
    if explicit:
        return explicit.rstrip("/")
    env_file = _find_free_stack_env_file()
    port = "18082"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("SEARXNG_PORT="):
                port = line.split("=", 1)[1].strip() or port
                break
    return f"http://localhost:{port}"


def _qdrant() -> tuple[str, str]:
    env_file = _find_free_stack_env_file()
    port = str(os.getenv("QDRANT_PORT", "16333")).strip()
    key = str(os.getenv("QDRANT_API_KEY", "")).strip()
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("QDRANT_PORT="):
                port = line.split("=", 1)[1].strip() or port
            if line.startswith("QDRANT_API_KEY=") and not key:
                key = line.split("=", 1)[1].strip()
    return f"http://localhost:{port}", key


def _find_free_stack_env_file() -> Path:
    candidates = [
        DATA_ROOT / "secure" / "free-stack.env",
        PROJECT_ROOT / "data" / "agent_space" / "secure" / "free-stack.env",
        BACKEND_ROOT / "data" / "agent_space" / "secure" / "free-stack.env",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()).lower() if candidate.exists() else str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return DATA_ROOT / "secure" / "free-stack.env"


def _extract_text(html: str, max_chars: int) -> tuple[str, str]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "form", "header", "iframe"]):
        tag.decompose()
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"\bcontent\b", re.IGNORECASE))
        or soup.find("body")
    )
    text = " ".join((main.get_text(" ", strip=True) if main else "").split())
    return title, text[:max_chars]


def _coerce_score(value: Any) -> float | None:
    try:
        if value is None:
            return None
        score = float(value)
        if score != score:  # NaN guard
            return None
        return score
    except Exception:
        return None


def _decode_bing_u_param(raw_value: str) -> str | None:
    token = unquote(str(raw_value or "")).strip()
    if not token:
        return None
    if token.lower().startswith("a1"):
        token = token[2:]
    token = token.replace("-", "+").replace("_", "/")
    padding = "=" * ((4 - (len(token) % 4)) % 4)
    candidates = [token + padding, token]
    for candidate in candidates:
        try:
            decoded = base64.b64decode(candidate, validate=False).decode("utf-8", errors="ignore").strip()
        except Exception:
            continue
        decoded_url = unquote(decoded).strip()
        if decoded_url.startswith("http://") or decoded_url.startswith("https://"):
            return decoded_url
    return None


def resolve_bing_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    params = parse_qs(parsed.query or "", keep_blank_values=True)
    looks_bing_redirect = (
        "bing.com" in host
        and (path.startswith("/ck/") or path.startswith("/aclick") or path.startswith("/fd/ls") or "u" in params)
    )
    if not looks_bing_redirect:
        return raw
    for encoded in list(params.get("u") or []):
        decoded = _decode_bing_u_param(encoded)
        if decoded:
            return decoded
    for key in ("url", "target", "r"):
        vals = list(params.get(key) or [])
        for val in vals:
            candidate = unquote(str(val or "")).strip()
            if candidate.startswith("http://") or candidate.startswith("https://"):
                return candidate
    return raw


def _clean_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    raw = resolve_bing_url(raw)
    parsed = urlparse(raw)
    if not parsed.scheme.startswith("http"):
        return ""
    return raw


def detect_query_intent(query: str) -> str:
    low = str(query or "").lower()
    if any(signal in low for signal in SHOPPING_SIGNALS):
        return "shopping"
    if any(signal in low for signal in NEWS_SIGNALS):
        return "news"
    return "general"


def score_relevance(query: str, rows: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    words = {word for word in _WORD_RE.findall(str(query or "").lower()) if len(word) > 3}
    if not words:
        return [(0.0, dict(row)) for row in rows]
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        entry = dict(row or {})
        text = (
            f"{entry.get('title', '')} {entry.get('snippet', '')} {entry.get('url', '')}"
        ).lower()
        matches = sum(1 for word in words if word in text)
        score = matches / max(len(words), 1)
        scored.append((float(score), entry))
    return scored


_HEAVY_MODELS = {"qwen2.5:32b", "qwen2.5:32b-instruct"}
_REWRITE_FALLBACK_MODEL = "qwen2.5-coder:7b"


async def rewrite_query_variants(query: str, timeout_seconds: float = 20.0) -> tuple[list[str], bool]:
    q = str(query or "").strip()
    if not q:
        return [], False
    configured = str(_settings.get().get("model", "qwen2.5-coder:14b"))
    # Use a lightweight model for query rewriting when the configured model is a heavy 32B
    # model — 32B is too slow for this short-lived task and often times out.
    model = _REWRITE_FALLBACK_MODEL if configured in _HEAVY_MODELS else configured
    prompt = "Rewrite this search query to maximize web search result quality. Output 2-3 search query variations, one per line, no explanation:\nQuery: " + q
    try:
        raw = await asyncio.wait_for(
            ollama_client.chat_full(model=model, messages=[{"role": "system", "content": "Return only rewritten queries."}, {"role": "user", "content": prompt}], temperature=0.1),
            timeout=timeout_seconds,
        )
        rows = [line.strip("-* \t") for line in str(raw or "").splitlines() if line.strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for row in rows:
            key = row.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(row)
            if len(deduped) >= 3:
                break
        if deduped:
            return deduped, True
    except Exception:
        logger.warning("Failed to rewrite search query via model; using original query", exc_info=True)
    return [q], False


async def search_searxng(query: str, limit: int = 8, *, intent: str = "general") -> list[dict[str, Any]]:
    categories = "general"
    if intent == "shopping":
        categories = "shopping,general"
    elif intent == "news":
        categories = "news,general"
    headers = dict(UA_HEADERS)
    headers["X-Forwarded-For"] = "127.0.0.1"
    headers["X-Real-IP"] = "127.0.0.1"
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=headers) as client:
        resp = await client.get(
            f"{_searxng_url()}/search",
            params={"q": query, "format": "json", "categories": categories, "language": "en"},
        )
        resp.raise_for_status()
        data = resp.json()
    out: list[dict[str, Any]] = []
    for row in list(data.get("results") or []):
        if not isinstance(row, dict):
            continue
        url = _clean_url(str(row.get("url") or ""))
        if not url:
            continue
        out.append(
            {
                "title": str(row.get("title") or "Untitled"),
                "url": url,
                "snippet": str(row.get("content") or ""),
                "provider": "searxng",
                "engine": str(row.get("engine") or "searxng"),
                "query": query,
                "score": _coerce_score(row.get("score")),
            }
        )
        if len(out) >= max(1, int(limit)):
            break
    return out


async def search_ddg(query: str, limit: int = 8, *, intent: str = "general") -> list[dict[str, Any]]:
    query_variants = [query]
    if intent == "shopping":
        query_variants.append(f"{query} price")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=UA_HEADERS) as client:
        for ddg_query in query_variants:
            resp = await client.get(DDG_API, params={"q": ddg_query, "format": "json", "no_html": "1", "skip_disambig": "1"})
            resp.raise_for_status()
            data = resp.json()
            abstract = str(data.get("Abstract") or "").strip()
            abstract_url = _clean_url(str(data.get("AbstractURL") or ""))
            if abstract and abstract_url and abstract_url.lower() not in seen:
                seen.add(abstract_url.lower())
                rows.append(
                    {
                        "title": str(data.get("Heading") or "DuckDuckGo"),
                        "url": abstract_url,
                        "snippet": abstract,
                        "provider": "duckduckgo",
                        "engine": "duckduckgo",
                        "query": ddg_query,
                        "score": None,
                    }
                )
            for topic in list(data.get("RelatedTopics") or []):
                if not isinstance(topic, dict):
                    continue
                text = str(topic.get("Text") or "").strip()
                url = _clean_url(str(topic.get("FirstURL") or ""))
                key = url.lower()
                if text and url and key not in seen:
                    seen.add(key)
                    rows.append(
                        {
                            "title": text[:120],
                            "url": url,
                            "snippet": text,
                            "provider": "duckduckgo",
                            "engine": "duckduckgo",
                            "query": ddg_query,
                            "score": None,
                        }
                    )
                if len(rows) >= max(1, int(limit)):
                    break
            if len(rows) >= max(1, int(limit)):
                break
    return rows


async def search_existing(query: str, limit: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rows = await asyncio.wait_for(
        legacy_web_search.search(query, n=max(1, min(10, int(limit)))),
        timeout=4.0,
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _clean_url(str(row.get("url") or ""))
        if not url:
            continue
        out.append(
            {
                "title": str(row.get("title") or "Untitled"),
                "url": url,
                "snippet": str(row.get("snippet") or ""),
                "provider": "existing_tool",
                "engine": "legacy_web_search",
                "query": query,
                "score": None,
            }
        )
    return out[: max(1, int(limit))]


async def search_wikipedia(query: str, limit: int = 3) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=UA_HEADERS) as client:
        resp = await client.get(WIKI_API, params={"action": "query", "list": "search", "srsearch": query, "srlimit": max(1, min(6, int(limit))), "format": "json", "origin": "*"})
        resp.raise_for_status()
        data = resp.json()
    out: list[dict[str, Any]] = []
    for row in list(data.get("query", {}).get("search", []) or [])[: max(1, int(limit))]:
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        out.append(
            {
                "title": title,
                "url": f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                "snippet": str(row.get("snippet") or ""),
                "provider": "wikipedia",
                "engine": "wikipedia",
                "query": query,
                "score": None,
            }
        )
    return out


async def search_bing(query: str, limit: int = 8) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=UA_HEADERS) as client:
        resp = await client.get(BING_SEARCH_URL, params={"q": query, "count": max(1, min(10, int(limit)))})
        resp.raise_for_status()
    soup = BeautifulSoup(str(resp.text or ""), "html.parser")
    rows: list[dict[str, Any]] = []
    for card in soup.select("li.b_algo"):
        link = card.select_one("h2 a")
        if link is None:
            continue
        url = _clean_url(str(link.get("href") or ""))
        if not url:
            continue
        title = str(link.get_text(" ", strip=True) or "Untitled")
        snippet_node = card.select_one(".b_caption p") or card.select_one("p")
        snippet = str(snippet_node.get_text(" ", strip=True) if snippet_node else "")
        rows.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "provider": "bing",
                "engine": "bing",
                "query": query,
                "score": None,
            }
        )
        if len(rows) >= max(1, int(limit)):
            break
    return rows


async def search_google(query: str, limit: int = 8) -> list[dict[str, Any]]:
    headers = dict(UA_HEADERS)
    headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=headers) as client:
        resp = await client.get(GOOGLE_SEARCH_URL, params={"q": query, "num": max(3, min(10, int(limit)))})
        resp.raise_for_status()
    soup = BeautifulSoup(str(resp.text or ""), "html.parser")
    rows: list[dict[str, Any]] = []
    # Common Google result containers.
    for card in soup.select("div.tF2Cxc, div.g"):
        link = card.select_one("a")
        if link is None:
            continue
        url = _clean_url(str(link.get("href") or ""))
        if not url:
            continue
        title_node = card.select_one("h3") or card.select_one("h2")
        title = str(title_node.get_text(" ", strip=True) if title_node else "Untitled")
        snippet_node = card.select_one("div.VwiC3b") or card.select_one("span.aCOpRe") or card.select_one("div.IsZvec")
        snippet = str(snippet_node.get_text(" ", strip=True) if snippet_node else "")
        rows.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "provider": "google",
                "engine": "google_html",
                "query": query,
                "score": None,
            }
        )
        if len(rows) >= max(1, int(limit)):
            break
    return rows


async def _parallel_search(queries: list[str], limit: int = 8, *, intent: str = "general") -> dict[str, Any]:
    async def _with_timeout(coro: Any, timeout: float = PARALLEL_PROVIDER_TIMEOUT_S) -> Any:
        return await asyncio.wait_for(coro, timeout=timeout)

    tasks: list[tuple[str, asyncio.Task]] = []
    for q in queries[:3]:
        tasks.append(("searxng", asyncio.create_task(_with_timeout(search_searxng(q, limit=limit, intent=intent)))))
        tasks.append(("bing", asyncio.create_task(_with_timeout(search_bing(q, limit=limit)))))
        tasks.append(("google", asyncio.create_task(_with_timeout(search_google(q, limit=limit)))))
        tasks.append(("duckduckgo", asyncio.create_task(_with_timeout(search_ddg(q, limit=limit, intent=intent)))))
        tasks.append(("existing", asyncio.create_task(_with_timeout(search_existing(q, limit=limit)))))
        tasks.append(("wikipedia", asyncio.create_task(_with_timeout(search_wikipedia(q, limit=min(3, limit))))))
    provider_rows: dict[str, list[dict[str, Any]]] = {
        "searxng": [],
        "bing": [],
        "google": [],
        "duckduckgo": [],
        "existing": [],
        "wikipedia": [],
    }
    errors: dict[str, str] = {}
    settled = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
    for (provider, _), result in zip(tasks, settled):
        if isinstance(result, Exception):
            if provider not in errors:
                errors[provider] = str(result)
            continue
        provider_rows[provider].extend(list(result or []))
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for provider in ("searxng", "bing", "google", "duckduckgo", "existing", "wikipedia"):
        for row in provider_rows.get(provider, []):
            url = str(row.get("url") or "").strip()
            key = url.lower()
            if not url or key in seen:
                continue
            seen.add(key)
            merged.append(row)
            if len(merged) >= 10:
                return {"rows": merged, "provider_rows": provider_rows, "errors": errors}
    return {"rows": merged, "provider_rows": provider_rows, "errors": errors}


async def fetch_page_content(url: str, *, max_chars: int = 2500) -> dict[str, Any]:
    raw_target = str(url or "").strip()
    target = _clean_url(raw_target) or raw_target
    if not target:
        return {"ok": False, "url": "", "text": "", "error": "empty_url"}
    try:
        headers = dict(UA_HEADERS)
        headers["User-Agent"] = FETCH_USER_AGENT
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, max_redirects=3, headers=headers) as client:
            resp = await client.get(target)
            resp.raise_for_status()
        title, text = _extract_text(resp.text, max_chars=max_chars)
        return {"ok": bool(text), "url": target, "title": title, "text": text}
    except Exception as exc:
        return {"ok": False, "url": target, "text": "", "error": str(exc)}


async def _fetch_via_jina_reader(url: str, max_chars: int = 12000) -> dict[str, Any]:
    target = str(url or "").strip()
    if not target:
        return {"ok": False, "url": target, "text": "", "error": "empty_url"}
    if not target.startswith("http://") and not target.startswith("https://"):
        target = f"https://{target}"
    reader_url = f"https://r.jina.ai/http://{target}"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=UA_HEADERS) as client:
            resp = await client.get(reader_url)
            resp.raise_for_status()
        raw = str(resp.text or "").strip()
        if not raw:
            return {"ok": False, "url": target, "text": "", "error": "empty_reader_response"}
        first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
        return {
            "ok": True,
            "url": target,
            "title": first_line[:160] if first_line else "",
            "text": raw[:max_chars],
            "provider": "jina_reader",
        }
    except Exception as exc:
        return {"ok": False, "url": target, "text": "", "error": str(exc)}


async def _qdrant_ensure_collection(size: int) -> bool:
    base, api_key = _qdrant()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key
    endpoint = f"{base}/collections/{COLLECTION}"
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, headers=headers) as client:
            status_resp = await client.get(endpoint)
            if status_resp.status_code == 200:
                return True
            if status_resp.status_code not in {400, 404}:
                return False
            create_resp = await client.put(endpoint, json={"vectors": {"size": int(size), "distance": "Cosine"}})
            return create_resp.status_code in {200, 201}
    except Exception:
        return False


async def _qdrant_lookup(query: str) -> dict[str, Any] | None:
    text = str(query or "").strip()
    if not text:
        return None
    try:
        vector = await ollama_client.embed(text)
        if not vector or not await _qdrant_ensure_collection(len(vector)):
            return None
        base, api_key = _qdrant()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["api-key"] = api_key
        endpoint = f"{base}/collections/{COLLECTION}/points/search"
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, headers=headers) as client:
            resp = await client.post(endpoint, json={"vector": vector, "limit": 1, "with_payload": True})
            resp.raise_for_status()
            rows = list(resp.json().get("result") or [])
        if not rows:
            return None
        top = rows[0]
        score = float(top.get("score") or 0.0)
        if score < CACHE_HIT_MIN:
            return None
        payload = dict(top.get("payload") or {})
        return {
            "score": score,
            "answer": str(payload.get("answer") or ""),
            "sources": list(payload.get("sources") or []),
            "ts": str(payload.get("ts") or ""),
        }
    except Exception:
        return None


async def _qdrant_store(query: str, answer: str, sources: list[dict[str, Any]]) -> bool:
    text = str(query or "").strip()
    if not text or not str(answer or "").strip():
        return False
    try:
        vector = await ollama_client.embed(text)
        if not vector or not await _qdrant_ensure_collection(len(vector)):
            return False
        base, api_key = _qdrant()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["api-key"] = api_key
        endpoint = f"{base}/collections/{COLLECTION}/points"
        body = {
            "points": [
                {
                    "id": str(uuid.uuid4()),
                    "vector": vector,
                    "payload": {"query": text, "answer": answer, "sources": sources, "ts": _now_iso()},
                }
            ]
        }
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, headers=headers) as client:
            resp = await client.put(endpoint, json=body)
            resp.raise_for_status()
        return True
    except Exception:
        return False


def _source_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        score = _coerce_score(row.get("score"))
        relevance = _coerce_score(row.get("relevance"))
        if score is None and relevance is not None:
            score = relevance
        out.append(
            {
                "id": idx,
                "title": str(row.get("title") or "Untitled"),
                "url": str(row.get("url") or ""),
                "snippet": str(row.get("snippet") or ""),
                "provider": str(row.get("provider") or ""),
                "engine": str(row.get("engine") or ""),
                "query": str(row.get("query") or ""),
                "score": score,
                "relevance": relevance,
            }
        )
    return out


def _chunk_text(text: str, size: int = 120) -> list[str]:
    raw = str(text or "")
    return [raw[i : i + size] for i in range(0, len(raw), size)] if raw else []


def _filter_provider_errors(errors: dict[str, str], rows: list[dict[str, Any]]) -> dict[str, str]:
    raw_errors = {
        str(k): str(v)
        for k, v in dict(errors or {}).items()
        if str(k).strip() and str(v).strip()
    }
    if not raw_errors:
        return {}
    if not rows:
        return raw_errors
    providers_with_rows = {str(row.get("provider") or "").strip().lower() for row in rows}
    has_searxng_rows = "searxng" in providers_with_rows
    if has_searxng_rows:
        # SearXNG is the primary aggregated source; hide secondary provider
        # transport failures when grounded results are already available.
        return {k: v for k, v in raw_errors.items() if str(k).strip().lower() in {"searxng"}}
    return raw_errors


def _fallback_answer(query: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return f"I could not retrieve live web results for '{query}'."
    lines = [f"I could not synthesize with Ollama right now, but found {len(sources)} sources:"]
    for idx, row in enumerate(sources[:8], start=1):
        lines.append(f"[{idx}] {row.get('title', 'Untitled')} — {row.get('url', '')}")
    return "\n".join(lines)


async def get_research_service_status(*, use_cache: bool = True) -> dict[str, Any]:
    global _service_status_cache_data, _service_status_cache_ts
    if use_cache and _service_status_cache_data is not None and (time.time() - _service_status_cache_ts) <= SERVICE_STATUS_CACHE_TTL_SECONDS:
        return dict(_service_status_cache_data)

    async def probe(name: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            req_headers = dict(UA_HEADERS)
            if headers:
                req_headers.update(headers)
            async with httpx.AsyncClient(timeout=0.75, follow_redirects=True, headers=req_headers) as client:
                resp = await client.get(url)
            return {"name": name, "ok": resp.status_code < 500, "status_code": int(resp.status_code), "url": url}
        except Exception as exc:
            return {"name": name, "ok": False, "status_code": 0, "url": url, "error": str(exc)}
    qdrant_url, _ = _qdrant()
    _, qdrant_api_key = _qdrant()
    qdrant_headers = {"api-key": qdrant_api_key} if qdrant_api_key else None
    rows = await asyncio.gather(
        probe("searxng", f"{_searxng_url()}/search?q=test&format=json"),
        probe("bing", f"{BING_SEARCH_URL}?q=test"),
        probe("google", f"{GOOGLE_SEARCH_URL}?q=test"),
        probe("duckduckgo", f"{DDG_API}?q=test&format=json&no_html=1&skip_disambig=1"),
        probe("qdrant", f"{qdrant_url}/collections", headers=qdrant_headers),
        return_exceptions=True,
    )
    status: dict[str, Any] = {}
    for row in rows:
        if isinstance(row, Exception):
            continue
        status[str(row.get("name") or "unknown")] = row
    try:
        status["ollama"] = {"name": "ollama", "ok": True, "model_count": len(await ollama_client.list_models())}
    except Exception as exc:
        status["ollama"] = {"name": "ollama", "ok": False, "model_count": 0, "error": str(exc)}
    _service_status_cache_data = dict(status)
    _service_status_cache_ts = time.time()
    return status


async def search_web(query: str, limit: int = 8) -> dict[str, Any]:
    text = str(query or "").strip()
    if not text:
        return {"ok": False, "offline": False, "query": "", "results": [], "provider": "none", "cached": False, "stale": False}
    cached = _cache_get("search", text, SEARCH_TTL)
    if cached is not None:
        return cached
    t0 = time.perf_counter()
    intent = detect_query_intent(text)
    rewritten, used_rewrite = await rewrite_query_variants(text, timeout_seconds=QUERY_REWRITE_TIMEOUT_S)
    search_data = await _parallel_search(rewritten[:3], limit=max(4, min(10, int(limit))), intent=intent)
    rows = list(search_data.get("rows") or [])[: max(1, min(10, int(limit)))]
    scored = score_relevance(text, rows)
    rows = []
    for relevance, row in sorted(scored, key=lambda item: item[0], reverse=True):
        entry = dict(row)
        entry["relevance"] = relevance
        if _coerce_score(entry.get("score")) is None:
            entry["score"] = relevance
        rows.append(entry)
    payload = {
        "ok": bool(rows),
        "offline": not bool(rows),
        "query": text,
        "intent": intent,
        "rewritten_queries": rewritten,
        "used_rewrite": used_rewrite,
        "results": _source_rows(rows),
        "provider": "multi",
        "providers_tried": ["searxng", "bing", "google", "duckduckgo", "existing", "wikipedia"],
        "provider_errors": _filter_provider_errors(dict(search_data.get("errors") or {}), rows),
        "timings": {"total": round(_perf_delta(t0), 4)},
        "cached": False,
        "stale": False,
    }
    if rows:
        _cache_put("search", text, payload)
        return payload
    return payload


async def fetch_web(url: str, max_chars: int = 12000) -> dict[str, Any]:
    raw_target = str(url or "").strip()
    target = _clean_url(raw_target) or raw_target
    if not target:
        return {"ok": False, "offline": False, "url": "", "error": "empty_url", "text": ""}
    cached = _cache_get("fetch", target, FETCH_TTL)
    if cached is not None:
        cached["text"] = str(cached.get("text") or "")[:max_chars]
        return cached
    data = await fetch_page_content(target, max_chars=max_chars)
    if not data.get("ok"):
        jina = await _fetch_via_jina_reader(target, max_chars=max_chars)
        if jina.get("ok"):
            payload = {
                "ok": True,
                "offline": False,
                "url": target,
                "title": str(jina.get("title") or ""),
                "text": str(jina.get("text") or ""),
                "provider": "jina_reader",
                "cached": False,
                "stale": False,
            }
            _cache_put("fetch", target, payload)
            return payload
        try:
            legacy_text = await legacy_web_search.fetch_page(target, max_chars=max_chars)
            clean_text = str(legacy_text or "").strip()
            if clean_text and not clean_text.lower().startswith("error fetching page:"):
                payload = {
                    "ok": True,
                    "offline": False,
                    "url": target,
                    "title": "",
                    "text": clean_text[:max_chars],
                    "provider": "legacy_fetch",
                    "cached": False,
                    "stale": False,
                }
                _cache_put("fetch", target, payload)
                return payload
        except Exception:
            logger.warning("Failed to process legacy fetch response for URL %s", target, exc_info=True)
        return {"ok": False, "offline": True, "url": target, "error": str(data.get("error") or "fetch_failed"), "text": ""}
    payload = {
        "ok": True,
        "offline": False,
        "url": target,
        "title": str(data.get("title") or ""),
        "text": str(data.get("text") or ""),
        "provider": "http_fetch",
        "cached": False,
        "stale": False,
    }
    _cache_put("fetch", target, payload)
    return payload


async def research_stream(query: str, *, force_live: bool = False, model: str | None = None, max_results: int = 10) -> AsyncGenerator[dict[str, Any], None]:
    user_query = str(query or "").strip()
    if not user_query:
        yield {"type": "error", "message": "Query cannot be empty."}
        yield {"type": "done", "ok": False, "answer": "", "sources": [], "timings": {}}
        return
    total_start = time.perf_counter()
    timings: dict[str, float] = {}
    if not force_live:
        exact = _exact_cache_get(user_query)
        if exact and str(exact.get("answer") or "").strip():
            answer = str(exact.get("answer") or "")
            cached_at = str(exact.get("ts") or "")
            yield {"type": "services", "services": await get_research_service_status(use_cache=True)}
            yield {"type": "step", "step": "query_rewrite", "status": "skipped"}
            yield {"type": "step", "step": "memory", "status": "done", "cache_status": "hit"}
            yield {"type": "step", "step": "search", "status": "skipped"}
            yield {"type": "step", "step": "read_pages", "status": "skipped"}
            yield {"type": "step", "step": "synthesis", "status": "skipped"}
            for chunk in _chunk_text(answer, size=200):
                yield {"type": "token", "text": chunk}
            timings["total"] = round(_perf_delta(total_start), 4)
            yield {
                "type": "memory_hit",
                "from_memory": True,
                "score": 1.0,
                "match_percent": 100.0,
                "cached_at": cached_at,
                "cached_age_label": _format_age_label(cached_at),
                "sources": list(exact.get("sources") or []),
            }
            yield {
                "type": "done",
                "ok": True,
                "from_memory": True,
                "answer": answer,
                "sources": list(exact.get("sources") or []),
                "timings": timings,
                "query": user_query,
                "rewritten_queries": [user_query],
            }
            return
    yield {"type": "services", "services": await get_research_service_status(use_cache=True)}

    t0 = time.perf_counter()
    yield {"type": "step", "step": "query_rewrite", "status": "running", "label": "Rewriting query..."}
    rewritten, used_rewrite = await rewrite_query_variants(user_query, timeout_seconds=QUERY_REWRITE_TIMEOUT_S)
    timings["query_rewrite"] = round(_perf_delta(t0), 4)
    logger.info("[research] query_rewrite: %.3fs", timings["query_rewrite"])
    yield {"type": "step", "step": "query_rewrite", "status": "done", "rewritten_queries": rewritten, "used_rewrite": used_rewrite}

    t0 = time.perf_counter()
    yield {"type": "step", "step": "memory", "status": "running", "label": "Checking memory (Qdrant)..."}
    memory = None if force_live else await _qdrant_lookup(user_query)
    timings["cache_check"] = round(_perf_delta(t0), 4)
    yield {"type": "step", "step": "memory", "status": "skipped" if force_live else "done", "cache_status": "hit" if memory else ("skipped" if force_live else "miss")}
    logger.info("[research] cache_check: %.3fs (%s)", timings["cache_check"], "hit" if memory else ("skipped" if force_live else "miss"))
    if memory and str(memory.get("answer") or "").strip():
        answer = str(memory.get("answer") or "")
        cached_at = str(memory.get("ts") or "")
        yield {"type": "step", "step": "search", "status": "skipped"}
        yield {"type": "step", "step": "read_pages", "status": "skipped"}
        yield {"type": "step", "step": "synthesis", "status": "skipped"}
        for chunk in _chunk_text(answer, size=140):
            yield {"type": "token", "text": chunk}
        timings["total"] = round(_perf_delta(total_start), 4)
        _exact_cache_put(user_query, answer, list(memory.get("sources") or []), ts_iso=cached_at or None)
        yield {
            "type": "memory_hit",
            "from_memory": True,
            "score": float(memory.get("score") or 0.0),
            "match_percent": round(float(memory.get("score") or 0.0) * 100.0, 1),
            "cached_at": cached_at,
            "cached_age_label": _format_age_label(cached_at),
            "sources": list(memory.get("sources") or []),
        }
        yield {"type": "done", "ok": True, "from_memory": True, "answer": answer, "sources": list(memory.get("sources") or []), "timings": timings, "query": user_query, "rewritten_queries": rewritten}
        return

    intent = detect_query_intent(user_query)
    t0 = time.perf_counter()
    yield {"type": "step", "step": "search", "status": "running", "label": "Searching SearXNG · Bing · Google · DDG · Wikipedia..."}
    search_data = await _parallel_search(rewritten[:3], limit=8, intent=intent)
    raw_rows = list(search_data.get("rows") or [])[: max(1, min(10, int(max_results)))]
    scored_rows = score_relevance(user_query, raw_rows)
    scored_rows.sort(key=lambda item: item[0], reverse=True)

    search_retried = False
    max_relevance = max((score for score, _ in scored_rows), default=0.0)
    if scored_rows and max_relevance < 0.2:
        search_retried = True
        retry_queries, _ = await rewrite_query_variants(
            f"{user_query} official sources",
            timeout_seconds=QUERY_REWRITE_TIMEOUT_S,
        )
        retry_search_data = await _parallel_search(
            retry_queries[:3] or [user_query],
            limit=8,
            intent=intent,
        )
        retry_rows = list(retry_search_data.get("rows") or [])[: max(1, min(10, int(max_results)))]
        retry_scored_rows = score_relevance(user_query, retry_rows)
        retry_scored_rows.sort(key=lambda item: item[0], reverse=True)
        retry_max_relevance = max((score for score, _ in retry_scored_rows), default=0.0)
        if retry_scored_rows and retry_max_relevance >= max_relevance:
            search_data = retry_search_data
            scored_rows = retry_scored_rows
            max_relevance = retry_max_relevance

    rows: list[dict[str, Any]] = []
    for relevance, row in scored_rows:
        entry = dict(row or {})
        entry["relevance"] = relevance
        if _coerce_score(entry.get("score")) is None:
            entry["score"] = relevance
        rows.append(entry)

    relevant_count = sum(1 for row in rows if float(row.get("relevance") or 0.0) >= 0.25)
    total_count = len(rows)
    context_rows = [row for row in rows if float(row.get("relevance") or 0.0) >= 0.25][:8]
    poor_relevance = bool(rows) and max_relevance < 0.25
    sources = _source_rows(rows)
    timings["parallel_search"] = round(_perf_delta(t0), 4)
    logger.info("[research] parallel_search: %.3fs (%d results)", timings["parallel_search"], len(rows))
    visible_provider_errors = _filter_provider_errors(dict(search_data.get("errors") or {}), rows)
    yield {
        "type": "step",
        "step": "search",
        "status": "done",
        "result_count": len(rows),
        "relevant_count": relevant_count,
        "intent": intent,
        "relevance_retry": search_retried,
        "provider_errors": visible_provider_errors,
    }
    if sources:
        yield {"type": "sources", "sources": sources}

    t0 = time.perf_counter()
    yield {"type": "step", "step": "read_pages", "status": "running", "label": "Reading top pages..."}
    searx_rows = list(dict(search_data.get("provider_rows") or {}).get("searxng") or [])
    deep_targets: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    for row in [*context_rows, *searx_rows, *rows]:
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        key = url.lower()
        if key in seen_targets:
            continue
        seen_targets.add(key)
        deep_targets.append(row)
        if len(deep_targets) >= 5:
            break
    deep_content_by_url: dict[str, str] = {}
    if deep_targets:
        fetched = await asyncio.gather(
            *[
                asyncio.create_task(fetch_page_content(str(row.get("url") or ""), max_chars=2500))
                for row in deep_targets
            ],
            return_exceptions=True,
        )
        for row, data in zip(deep_targets, fetched):
            url = str(row.get("url") or "").strip()
            fallback = str(row.get("snippet") or "")[:2500]
            if isinstance(data, Exception):
                deep_content_by_url[url] = fallback
                continue
            text = str(dict(data).get("text") or fallback)[:2500]
            deep_content_by_url[url] = text
    timings["page_fetch"] = round(_perf_delta(t0), 4)
    logger.info("[research] page_fetch: %.3fs (%d pages)", timings["page_fetch"], len(deep_content_by_url))
    yield {"type": "step", "step": "read_pages", "status": "done", "fetched_pages": len(deep_content_by_url)}

    t0 = time.perf_counter()
    yield {"type": "step", "step": "synthesis", "status": "running", "label": "Synthesizing answer..."}
    if not rows:
        fallback = _fallback_answer(user_query, sources)
        for chunk in _chunk_text(fallback, size=140):
            yield {"type": "token", "text": chunk}
        await _qdrant_store(user_query, fallback, sources)
        _exact_cache_put(user_query, fallback, sources)
        timings["synthesis"] = round(_perf_delta(t0), 4)
        timings["total"] = round(_perf_delta(total_start), 4)
        yield {"type": "step", "step": "synthesis", "status": "done", "mode": "raw_results"}
        yield {
            "type": "done",
            "ok": True,
            "from_memory": False,
            "answer": fallback,
            "sources": sources,
            "timings": timings,
            "query": user_query,
            "rewritten_queries": rewritten,
            "provider_errors": visible_provider_errors,
            "raw_mode": True,
        }
        return

    context_lines = ["Sources searched: SearXNG, DuckDuckGo, Wikipedia", ""]
    if poor_relevance:
        context_lines.append(
            "Relevance check: search results appear weak for this query. Use caution and avoid over-claiming."
        )
        context_lines.append("")
    for idx, row in enumerate(context_rows[:8], start=1):
        url = str(row.get("url") or "")
        relevance_pct = round(float(row.get("relevance") or 0.0) * 100)
        context_lines.append(f"[{idx}] {row.get('title', 'Untitled')} (relevance: {relevance_pct}%)")
        context_lines.append(f"URL: {url}")
        context_lines.append(
            deep_content_by_url.get(url)
            or str(row.get("snippet") or "No content extracted.")
        )
        context_lines.append("")
    if not context_rows:
        context_lines.append("No high-relevance source excerpts were extracted.")
        context_lines.append("")
    context = "\n".join(context_lines)
    cfg = _settings.get()
    model_name = str(model or cfg.get("model", "qwen2.5-coder:14b"))
    system_prompt = (
        f"You are a precise web research assistant. Today is {datetime.now().strftime('%Y-%m-%d')}.\n"
        "You will be given search results with a relevance score (0–100%) for each source.\n"
        "Rules:\n"
        "- Only cite [N] when that source's content directly supports the specific claim you are making.\n"
        "  Do NOT cite a source just because it appeared in search results.\n"
        "- Do NOT draw conclusions that go beyond what the source text actually states.\n"
        "- Sources with low relevance (below ~40%) are weak matches — treat their content cautiously\n"
        "  and do not cite them for specific factual claims.\n"
        "- If the sources do not contain enough information to answer the query, say so explicitly.\n"
        "  Then, if you have relevant training knowledge, add a clearly labelled section:\n"
        "  'Based on general knowledge (not from search results): ...'\n"
        "- Never blend training knowledge with source citations in a way that makes training\n"
        "  knowledge appear sourced.\n"
        "- Be direct. No filler. No 'Certainly'."
    )
    prompt = (
        f"Query: {user_query}\n"
        f"Intent detected: {intent}\n"
        f"Relevant results found: {relevant_count} of {total_count}\n\n"
        f"{context}\n\n"
        "Answer the query using only what the sources above actually state. "
        "Cite [N] only when that source directly supports the claim. "
        "If the sources are insufficient, say so, then provide general knowledge clearly labelled as such."
    )
    answer_parts: list[str] = []
    raw_mode = False
    first_token_t0 = time.perf_counter()
    first_token_seen = False
    try:
        async for chunk in ollama_client.generate(model=model_name, prompt=prompt, system=system_prompt, stream=True, temperature=0.2):
            if not first_token_seen:
                first_token_seen = True
                timings["ollama_first_token"] = round(_perf_delta(first_token_t0), 4)
                logger.info("[research] ollama_first_token: %.3fs", timings["ollama_first_token"])
            answer_parts.append(chunk)
            yield {"type": "token", "text": chunk}
    except Exception as exc:
        logger.warning("Ollama synthesis failed: %s", exc)
        raw_mode = True
        fallback = _fallback_answer(user_query, sources)
        answer_parts = [fallback]
        if not first_token_seen:
            timings["ollama_first_token"] = round(_perf_delta(first_token_t0), 4)
        for chunk in _chunk_text(fallback, size=140):
            yield {"type": "token", "text": chunk}
    answer = "".join(answer_parts).strip() or _fallback_answer(user_query, sources)
    await _qdrant_store(user_query, answer, sources)
    _exact_cache_put(user_query, answer, sources)
    timings["synthesis"] = round(_perf_delta(t0), 4)
    timings["total"] = round(_perf_delta(total_start), 4)
    logger.info("[research] synthesis: %.3fs", timings["synthesis"])
    logger.info("[research] total: %.3fs", timings["total"])
    yield {"type": "step", "step": "synthesis", "status": "done", "raw_fallback": raw_mode}
    yield {"type": "done", "ok": True, "from_memory": False, "answer": answer, "sources": sources, "timings": timings, "query": user_query, "rewritten_queries": rewritten, "provider_errors": visible_provider_errors, "raw_mode": raw_mode}


async def research_once(query: str, *, force_live: bool = False, model: str | None = None, max_results: int = 10) -> dict[str, Any]:
    final: dict[str, Any] = {"ok": False, "answer": "", "sources": [], "timings": {}}
    chunks: list[str] = []
    async for event in research_stream(query, force_live=force_live, model=model, max_results=max_results):
        if str(event.get("type")) == "token":
            chunks.append(str(event.get("text") or ""))
        if str(event.get("type")) == "done":
            final = dict(event)
    if not final.get("answer"):
        final["answer"] = "".join(chunks)
    return final


async def warm_research_memory_collection(seed_text: str = "research cache warmup") -> dict[str, Any]:
    """Ensure Qdrant research memory collection exists with auto-detected embedding size."""
    try:
        vector = await ollama_client.embed(seed_text)
        if not vector:
            return {"ok": False, "reason": "empty_embedding"}
        ok = await _qdrant_ensure_collection(len(vector))
        return {"ok": bool(ok), "vector_size": len(vector)}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
