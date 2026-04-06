"""Chat API — streaming SSE responses with RAG augmentation."""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Optional
from urllib.parse import quote_plus, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_space.web_research import fetch_web, search_web
from agents.judge import judge_response, should_judge, JudgeVerdict
from agents.self_consistency import self_consistent_math
from config.inference_params import get_inference_params
from config.models import MODEL_ROUTES, get_speed_mode
from config.settings import (
    LAYERED_REVIEW_ENABLED,
    REVIEW_MODEL_ROLE,
    COMPARE_MODELS_ENABLED,
    COMPARE_MODEL_A_ROLE,
    COMPARE_MODEL_B_ROLE,
    JUDGE_MODEL_ROLE,
    OLLAMA_NPU_BASE_URL,
)
from memory import chat_context, chat_memory_jobs, cross_chat_memory
from memory import vectordb, session as session_store
from memory import chat_store
from models import ollama_client
from models.prompts import build_rag_prompt, load_style_profile, build_style_system_prompt
from models.router import get_model_config, get_current_model, set_current_model, get_compare_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def _schedule_memory_update(session_id: str, user_msg: str, assistant_msg: str) -> None:
    try:
        snap = chat_memory_jobs.normalize_snapshot(session_store.get_history(session_id))
        chat_memory_jobs.schedule_after_turn(session_id, user_msg, assistant_msg, snap)
    except Exception:
        logger.debug("memory schedule skipped", exc_info=True)


# ── Request / Response Schemas ─────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    mode: str = "chat"
    session_id: str = "default"  # Chat ID: history is scoped to this chat only; other chats are saved but not used here
    history: list[dict] = []    # Message history for this chat only (client sends current chat's messages)
    model_override: str | None = None
    has_image: bool = False
    image: str | None = None
    # Agent Space markdown skills (SKILL.md) — injected into system prompt like Claude-style skill packs.
    skill_slugs: list[str] = []
    auto_select_skills: bool = False


# ── Helpers ────────────────────────────────────────────────────────────

_FILE_QUERIES = re.compile(
    r"what files|what documents|what sources|what do you have|what.*access",
    re.IGNORECASE,
)

_AUTO_WEB_RESEARCH_HINTS = re.compile(
    r"latest|recent|today|current|right now|compare|competition|competitor|market|trend|pricing|prices|price of|cost of|how much|msrp|retail price|for sale|in stock|look up|search|news|benchmark",
    re.IGNORECASE,
)

_LIVE_WEB_REQUIRED_HINTS = re.compile(
    r"latest|recent|today|current|right now|real[- ]time|live",
    re.IGNORECASE,
)

_PRICE_QUERY_HINTS = re.compile(
    r"price|prices|pricing|cost|how much|deal|sale",
    re.IGNORECASE,
)

_COMMERCE_QUERY_HINTS = re.compile(
    r"store|retail|retailer|shop|shopping|buy|purchase|in stock|inventory|msrp|sku|coupon|discount|from | at | on ",
    re.IGNORECASE,
)

_DOMAIN_OR_BRAND_HINTS = re.compile(
    r"[a-z0-9.-]+\.(com|net|org)\b|dick'?s|amazon|walmart|target|costco|best buy|nike|adidas|rawlings|wilson|franklin",
    re.IGNORECASE,
)

_KNOWLEDGE_CUTOFF_HINTS = re.compile(
    r"knowledge cutoff|as of (my|the) last update|i (do not|don't) have (real-time|live) data",
    re.IGNORECASE,
)
_QUERY_WORDS = re.compile(r"[a-z0-9]+")
_COMMON_QUERY_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "can",
    "could",
    "do",
    "for",
    "from",
    "get",
    "give",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "much",
    "my",
    "of",
    "on",
    "or",
    "please",
    "price",
    "prices",
    "show",
    "tell",
    "the",
    "to",
    "what",
    "where",
    "with",
}
_COMMON_SPELLING_FIXES: dict[str, str] = {
    "frankling": "franklin",
    "frankin": "franklin",
    "franlkin": "franklin",
    "dicks": "dick's",
    "dickssportinggoods": "dick's sporting goods",
    "insta": "instagram",
}
_RETAIL_PRIORITY_DOMAINS = (
    "instagram.com",
    "dickssportinggoods.com",
    "franklinsports.com",
    "amazon.com",
    "walmart.com",
    "ebay.com",
    "target.com",
)


def _chat_auto_web_research_enabled() -> bool:
    try:
        from agent_space.runtime import settings_store
        cfg = settings_store.get()
        return bool(cfg.get("chat_auto_web_research_enabled", True))
    except ImportError:
        return True


def _normalize_live_query_text(message: str) -> str:
    text = str(message or "").strip().lower()
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text)
    for wrong, right in _COMMON_SPELLING_FIXES.items():
        normalized = re.sub(rf"\b{re.escape(wrong)}\b", right, normalized)
    normalized = normalized.replace("power strap", "powerstrap")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _build_focus_query(message: str) -> str:
    normalized = _normalize_live_query_text(message)
    if not normalized:
        return ""
    tokens = [tok for tok in _QUERY_WORDS.findall(normalized) if tok and tok not in _COMMON_QUERY_STOP_WORDS]
    if not tokens:
        return normalized
    # Keep high-signal product words first and keep query concise.
    focused = " ".join(tokens[:10]).strip()
    if _PRICE_QUERY_HINTS.search(normalized) and not re.search(r"\b(price|cost|pricing)\b", focused, re.IGNORECASE):
        focused = f"{focused} price"
    return focused


def _should_auto_web_research(message: str, mode: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    if str(mode).strip().lower() in {"research", "browser"}:
        return True
    if not _chat_auto_web_research_enabled():
        return False
    if _AUTO_WEB_RESEARCH_HINTS.search(text):
        return True
    return _is_live_store_price_query(text)


def _is_live_store_price_query(message: str) -> bool:
    text = str(message or "")
    if not _PRICE_QUERY_HINTS.search(text):
        return False
    if _LIVE_WEB_REQUIRED_HINTS.search(text):
        return True
    if _COMMERCE_QUERY_HINTS.search(text):
        return True
    if _DOMAIN_OR_BRAND_HINTS.search(text):
        return True
    if re.search(r"\b(price|cost)\s+of\b", text, re.IGNORECASE):
        return True
    return False


def _requires_live_web_answer(message: str) -> bool:
    text = str(message or "")
    if _is_live_store_price_query(text):
        return True
    if not _LIVE_WEB_REQUIRED_HINTS.search(text):
        return False
    if _PRICE_QUERY_HINTS.search(text):
        return True
    if re.search(r"\b(stock|weather|score|schedule|news|rate|price)\b", text, re.IGNORECASE):
        return True
    return False


def _build_web_queries(message: str) -> list[str]:
    text = str(message or "").strip()
    if not text:
        return []
    low = _normalize_live_query_text(text) or text.lower()
    focused = _build_focus_query(text)
    queries = [text]
    if low and low != text.lower():
        queries.append(low)
    if focused:
        queries.append(focused)
    queries.append(f"{focused or text} official source")

    if "dicks sporting goods" in low or "dick's sporting goods" in low or "dickssportinggoods" in low:
        queries.append(f"site:dickssportinggoods.com {focused or text}")
    if _PRICE_QUERY_HINTS.search(low):
        queries.append(f"{focused or text} official store price")
        queries.append(f"{focused or text} in stock price")
        queries.append(f"site:amazon.com {focused or text}")
        queries.append(f"site:walmart.com {focused or text}")
        queries.append(f"site:ebay.com {focused or text}")
    if "instagram" in low:
        platform_clean_focus = re.sub(r"\binstagram\b", "", focused or text, flags=re.IGNORECASE).strip() or (focused or text)
        queries.append(f"site:instagram.com {platform_clean_focus}")
        queries.append(f"instagram {platform_clean_focus} price")
    if not _LIVE_WEB_REQUIRED_HINTS.search(low):
        queries.append(f"latest {focused or text}")
    deduped: list[str] = []
    seen: set[str] = set()
    for q in queries:
        k = q.lower().strip()
        if not k or k in seen:
            continue
        seen.add(k)
        deduped.append(q)
    return deduped[:10]


def _domain_from_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return "unknown"
    host = (urlparse(raw).netloc or "").strip().lower()
    if not host:
        return "unknown"
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"


def _coerce_score(value: object) -> float | None:
    try:
        if value is None:
            return None
        score = float(value)
        if score != score:  # NaN guard
            return None
        return max(0.0, min(1.0, score))
    except (TypeError, ValueError):
        return None


def _score_source_relevance(query: str, title: str, snippet: str, url: str) -> float:
    words = {word for word in _QUERY_WORDS.findall(str(query or "").lower()) if len(word) > 3}
    if not words:
        return 0.0
    text = f"{title} {snippet} {url}".lower()
    matches = sum(1 for word in words if word in text)
    return max(0.0, min(1.0, matches / max(len(words), 1)))


def _build_direct_retailer_fallback_urls(message: str) -> list[str]:
    text = str(message or "").strip()
    if not text:
        return []
    low = _normalize_live_query_text(text) or text.lower()
    urls: list[str] = []
    focus = _build_focus_query(text)
    normalized = re.sub(r"[^a-z0-9\s]", " ", focus or low)
    tokens = [t for t in normalized.split() if t and t not in {"what", "is", "the", "of", "from", "for", "and", "with"}]
    query_terms = " ".join(tokens[:8]) or low
    encoded_terms = quote_plus(query_terms)

    if "dicks sporting goods" in low or "dick's sporting goods" in low or "dickssportinggoods" in low:
        urls.append(f"https://www.dickssportinggoods.com/search/SearchDisplay?searchTerm={encoded_terms}")
        if "batting glove" in low or "batting gloves" in low:
            urls.append("https://www.dickssportinggoods.com/f/baseball-batting-gloves")
    if "instagram" in low:
        urls.append(f"https://www.instagram.com/explore/search/keyword/?q={encoded_terms}")
    if _PRICE_QUERY_HINTS.search(low):
        urls.append(f"https://www.amazon.com/s?k={encoded_terms}")
        urls.append(f"https://www.walmart.com/search?q={encoded_terms}")
        urls.append(f"https://www.ebay.com/sch/i.html?_nkw={encoded_terms}")
    if "franklin" in low:
        urls.append(f"https://franklinsports.com/search?q={encoded_terms}")

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        key = url.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(url)
    return deduped[:6]


def _response_looks_stale_for_live_request(response_text: str) -> bool:
    text = str(response_text or "").strip()
    if not text:
        return False
    return bool(_KNOWLEDGE_CUTOFF_HINTS.search(text))


def _build_live_source_fallback_response(sources: list[dict], user_message: str) -> str:
    lines: list[str] = []
    for src in sources[:5]:
        source = str(src.get("source") or "").strip()
        text = str(src.get("text") or "").strip()
        if not source and not text:
            continue
        label = source or "source"
        snippet = text[:160] if text else "No snippet extracted."
        lines.append(f"- {label}: {snippet}")
    if not lines:
        return (
            "I could not reliably extract live details for this current-data request. "
            f"Please re-run with Research mode for: {user_message}"
        )
    return (
        "I performed live web lookup for this request. Here are the most relevant source snippets:\n"
        + "\n".join(lines)
        + "\n\nUse the linked sources to confirm the latest exact values/SKUs."
    )


def _source_url(value: str) -> str:
    raw = str(value or "").strip()
    return raw if raw.startswith(("http://", "https://")) else ""


# ── Headless browser capture for Chat (Playwright via Agent Space) ─────

_URL_IN_MESSAGE = re.compile(r"https?://[^\s\>)\"']+", re.IGNORECASE)
_GITHUB_PROFILE_PHRASE = re.compile(
    r"(?:github|gh)\s+(?:page|profile|account|user)\s+(?:for\s+|of\s+|my\s+)?@?"
    r"([A-Za-z0-9](?:[A-Za-z0-9_-]{0,38}[A-Za-z0-9])?)",
    re.IGNORECASE,
)
_GITHUB_PAGE_USERNAME = re.compile(
    r"github\s+page\s+([A-Za-z0-9](?:[A-Za-z0-9_-]{0,38}[A-Za-z0-9])?)",
    re.IGNORECASE,
)
_CHAT_BROWSER_VERBS = re.compile(
    r"screenshot|screen\s*shot|capture\s+(?:a\s+)?(?:page|site|website)|open\s+(?:a\s+)?browser|"
    r"show\s+me\s+what|navigate\s+to|go\s+to\s+(?:the\s+)?(?:page|site)|"
    r"what(?:'s|s| is)\s+on\s+(?:the\s+)?(?:page|site)|take\s+a\s+picture\s+of\s+(?:the\s+)?(?:page|site)",
    re.IGNORECASE,
)


def _should_attempt_chat_browser_capture(message: str, chat_request_mode: str) -> bool:
    rm = str(chat_request_mode or "").strip().lower()
    if rm == "browser":
        return True
    text = str(message or "").strip()
    if not text:
        return False
    if not _CHAT_BROWSER_VERBS.search(text):
        return False
    if _URL_IN_MESSAGE.search(text):
        return True
    if _GITHUB_PROFILE_PHRASE.search(text):
        return True
    if _GITHUB_PAGE_USERNAME.search(text):
        return True
    if re.search(r"github\.com/[\w.-]+", text, re.IGNORECASE):
        return True
    return False


def _extract_page_capture_url(message: str) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None
    m = _URL_IN_MESSAGE.search(text)
    if m:
        return m.group(0).rstrip(").,;]'\"")
    m2 = _GITHUB_PROFILE_PHRASE.search(text)
    if m2 and m2.group(1).strip():
        return f"https://github.com/{m2.group(1).strip()}"
    m3 = re.search(r"github\.com/([\w.-]+)/?", text, re.IGNORECASE)
    if m3:
        return f"https://github.com/{m3.group(1)}"
    m4 = _GITHUB_PAGE_USERNAME.search(text)
    if m4 and m4.group(1).strip():
        return f"https://github.com/{m4.group(1).strip()}"
    return None


async def _chat_playwright_screenshot(url: str) -> tuple[str | None, str | None, str]:
    """Return (raw_base64_png, error_message, resolved_url)."""
    u = str(url or "").strip()
    if not u:
        return None, "No URL to open.", ""
    try:
        from agent_space.runtime import browser_manager
    except ImportError:
        return None, "Browser automation is not available (Agent Space runtime missing).", u

    opened = await browser_manager.open_session(url=u, headless=True)
    if not opened.get("success"):
        err = str(opened.get("error") or "Failed to open browser session.")
        return None, err, u
    sid = str(opened.get("session_id") or "")
    if not sid:
        return None, "Browser session did not return session_id.", u
    try:
        shot = await browser_manager.screenshot(sid, full_page=False)
        if not shot.get("success"):
            return None, str(shot.get("error") or "Screenshot failed."), u
        b64 = shot.get("image_base64")
        if not isinstance(b64, str) or not b64.strip():
            return None, "Screenshot returned no image data.", u
        final = str(shot.get("url") or opened.get("url") or u)
        return b64.strip(), None, final
    finally:
        try:
            await browser_manager.close_session(sid)
        except Exception:
            logger.debug("chat browser close_session failed", exc_info=True)


async def _build_auto_web_research_context(
    message: str,
    limit: int = 8,
    fetch_details: bool = False,
) -> tuple[str, list[dict], dict]:
    normalized_message = _normalize_live_query_text(message) or str(message or "")
    relevance_query = _build_focus_query(message) or normalized_message
    strict_relevance_floor = 0.2 if _is_live_store_price_query(message) else 0.12

    queries = _build_web_queries(message)
    if not queries:
        return "", [], {"ok": False, "offline": False, "results": 0, "queries": []}

    all_rows: list[dict] = []
    offline_all = True
    per_query_limit = max(3, min(8, max(1, int(limit))))
    search_tasks = [search_web(query, limit=per_query_limit) for query in queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    for query, result in zip(queries, search_results):
        if isinstance(result, Exception):
            continue
        offline_all = offline_all and bool(result.get("offline"))
        if not bool(result.get("ok")):
            continue
        rows = list(result.get("results") or [])
        for row in rows:
            if not isinstance(row, dict):
                continue
            enriched = dict(row)
            enriched["_query"] = query
            url = str(row.get("url") or "")
            title = str(row.get("title") or "")
            snippet = str(row.get("snippet") or "")
            score = _coerce_score(row.get("relevance"))
            if score is None:
                score = _coerce_score(row.get("score"))
            if score is None:
                score = _score_source_relevance(relevance_query, title, snippet, url)
            enriched["_domain"] = _domain_from_url(url)
            domain = str(enriched.get("_domain") or "").lower()
            if any(priority in domain for priority in _RETAIL_PRIORITY_DOMAINS):
                score = max(float(score or 0.0), min(1.0, float(score or 0.0) + 0.18))
            if "instagram" in normalized_message and "instagram.com" in domain:
                score = max(float(score or 0.0), 0.45)
            enriched["_score"] = score
            all_rows.append(enriched)

    if all_rows:
        strongest = max(float(_coerce_score(row.get("_score")) or 0.0) for row in all_rows)
        if strongest < strict_relevance_floor:
            # Discard weak rows and use direct-source fallback path.
            all_rows = []

    if not all_rows:
        fallback_urls = _build_direct_retailer_fallback_urls(message)
        fallback_snippets: list[str] = []
        fallback_sources: list[dict] = []
        fallback_ok = False
        fallback_offline = True
        if fallback_urls:
            fallback_tasks = [fetch_web(url, max_chars=2400) for url in fallback_urls]
            fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            for url, fetched in zip(fallback_urls, fallback_results):
                if isinstance(fetched, Exception):
                    continue
                if not bool(fetched.get("ok")):
                    fallback_offline = fallback_offline and bool(fetched.get("offline", True))
                    continue
                fallback_ok = True
                fallback_offline = False
                title = str(fetched.get("title") or "Fetched page")
                text = str(fetched.get("text") or "").strip()
                excerpt = " ".join(text.split())[:320]
                domain = _domain_from_url(url)
                fallback_snippets.append(f"- {title} ({url}) [domain: {domain}]: {excerpt or 'No text extracted.'}")
                fallback_sources.append(
                    {
                        "text": excerpt[:200],
                        "source": url,
                        "score": _score_source_relevance(relevance_query, title, excerpt, url),
                        "domain": domain,
                    }
                )
        if fallback_ok and fallback_sources:
            context = (
                "Automatic web research context (direct-source fallback):\n"
                f"- Queries executed: {len(queries)}\n"
                f"- Distinct domains: {len({_domain_from_url(str(s.get('source') or '')) for s in fallback_sources})}\n"
                + "\n".join(fallback_snippets)
            )
            return context, fallback_sources, {
                "ok": True,
                "offline": False,
                "results": len(fallback_sources),
                "domain_count": len({_domain_from_url(str(s.get('source') or '')) for s in fallback_sources}),
                "queries": queries,
                "fetched_pages": len(fallback_sources),
            }
        return "", [], {"ok": False, "offline": (offline_all and fallback_offline), "results": 0, "queries": queries, "domain_count": 0, "fetched_pages": 0}

    deduped_rows: list[dict] = []
    seen_urls: set[str] = set()
    for row in all_rows:
        url = str(row.get("url") or "").strip()
        key = url or str(row.get("title") or "").strip().lower()
        if key and key in seen_urls:
            continue
        if key:
            seen_urls.add(key)
        deduped_rows.append(row)

    domain_buckets: dict[str, list[dict]] = {}
    for row in deduped_rows:
        domain = str(row.get("_domain") or "unknown").strip().lower() or "unknown"
        domain_buckets.setdefault(domain, []).append(row)
    for domain in list(domain_buckets.keys()):
        domain_buckets[domain].sort(key=lambda row: float(_coerce_score(row.get("_score")) or 0.0), reverse=True)

    selected_rows: list[dict] = []
    target = max(1, min(8, int(limit)))
    # Round-robin across domains to maximize source diversity.
    while len(selected_rows) < target:
        progressed = False
        for domain in sorted(domain_buckets.keys()):
            bucket = domain_buckets.get(domain) or []
            if not bucket:
                continue
            selected_rows.append(bucket.pop(0))
            progressed = True
            if len(selected_rows) >= target:
                break
        if not progressed:
            break

    snippets: list[str] = []
    sources: list[dict] = []
    for row in selected_rows:
        title = str(row.get("title") or "Untitled")
        url = str(row.get("url") or "")
        snippet = str(row.get("snippet") or "")
        domain = str(row.get("_domain") or "unknown")
        query_used = str(row.get("_query") or "")
        line = f"- {title}"
        if url:
            line += f" ({url})"
        if domain:
            line += f" [domain: {domain}]"
        if snippet:
            line += f": {snippet}"
        snippets.append(line)
        score = _coerce_score(row.get("_score"))
        if score is None:
            score = _score_source_relevance(relevance_query, title, snippet, url)
        sources.append(
            {
                "text": snippet[:200],
                "source": url or title,
                "score": score,
                "query": query_used,
                "domain": domain,
            }
        )

    fetched_pages = 0
    # Even non-live prompts fetch a small sample to improve reference quality.
    fetch_budget = min(4, len(selected_rows)) if fetch_details else min(2, len(selected_rows))
    if fetch_budget > 0:
        fetch_rows = [row for row in selected_rows[:fetch_budget] if str(row.get("url") or "").strip()]
        fetch_tasks = [fetch_web(str(row.get("url") or "").strip(), max_chars=2200) for row in fetch_rows]
        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        for row, fetched in zip(fetch_rows, fetch_results):
            if isinstance(fetched, Exception):
                continue
            if not bool(fetched.get("ok")):
                continue
            fetched_pages += 1
            url = str(row.get("url") or "").strip()
            title = str(fetched.get("title") or row.get("title") or "Fetched page")
            text = str(fetched.get("text") or "").strip()
            excerpt = " ".join(text.split())[:280]
            domain = _domain_from_url(url)
            if excerpt:
                base_score = _coerce_score(row.get("_score")) or 0.0
                excerpt_score = _score_source_relevance(relevance_query, title, excerpt, url)
                snippets.append(f"- {title} ({url}) [domain: {domain}]: {excerpt}")
                sources.append(
                    {
                        "text": excerpt,
                        "source": url,
                        "score": max(base_score, excerpt_score),
                        "domain": domain,
                    }
                )

    unique_domains = sorted(
        {
            str(row.get("_domain") or "").strip().lower()
            for row in selected_rows
            if str(row.get("_domain") or "").strip()
        }
    )
    context = (
        "Automatic web research context (multi-source reference pack):\n"
        f"- Queries executed: {len(queries)}\n"
        f"- Distinct domains: {len(unique_domains)}\n"
        + ("\n" + "\n".join(snippets) if snippets else "")
    )
    return context, sources, {
        "ok": True,
        "offline": False,
        "results": len(selected_rows),
        "domain_count": len(unique_domains),
        "queries": queries,
        "fetched_pages": fetched_pages,
    }


async def _run_review(user_message: str, assistant_response: str) -> tuple[str, str | None]:
    """Run reviewer model to confirm or correct the response. Uses NPU when OLLAMA_NPU_BASE_URL is set."""
    try:
        rev_cfg = get_model_config(REVIEW_MODEL_ROLE)
        review_system = (
            "You are a critic. Review the assistant response for correctness and clarity. "
            "Reply with either: CONFIRMED - [brief reason] or CORRECTED: [corrected full response]. Be brief."
        )
        review_user = f"User question: {user_message}\n\nAssistant response: {assistant_response}"
        review_messages = [
            {"role": "system", "content": review_system},
            {"role": "user", "content": review_user},
        ]
        review_text = await ollama_client.chat_full(
            rev_cfg.model, review_messages, temperature=0.3,
            base_url=OLLAMA_NPU_BASE_URL,
        )
        if review_text.strip().upper().startswith("CORRECTED:"):
            corrected = review_text.split(":", 1)[-1].strip()
            if corrected:
                return corrected, review_text
        return assistant_response, review_text
    except Exception as e:
        logger.warning("Review layer failed: %s", e)
        return assistant_response, None


def _judge_meta(verdict: JudgeVerdict) -> dict:
    """Build judge metadata for SSE done payload."""
    return {
        "ran": True,
        "passed": verdict.passed,
        "confidence": verdict.confidence.value,
        "issues": verdict.issues,
        "suggestions": verdict.suggestions,
        "judge_model": verdict.judge_model,
        "was_revised": not verdict.passed and verdict.revised_response is not None,
    }


async def _stream_chat(
    message: str,
    mode: str,
    session_id: str,
    history: list[dict],
    model_override: str | None = None,
    has_image: bool = False,
    image_b64: str | None = None,
    skill_slugs: list[str] | None = None,
    auto_select_skills: bool = False,
) -> AsyncGenerator[str, None]:
    """Core streaming logic — RAG retrieval → prompt build → Ollama stream."""

    chat_request_mode = str(mode or "chat").strip().lower()
    browser_png_b64: str | None = None
    browser_capture_url = ""

    # Check for "what files do you have?" shortcut
    if _FILE_QUERIES.search(message):
        sources = await vectordb.list_sources()
        if sources:
            answer = "I have access to these sources:\n" + "\n".join(
                f"- {s}" for s in sources
            )
        else:
            answer = "I don't have any documents indexed yet. Upload some files first!"
        yield f"data: {json.dumps({'text': answer, 'done': True, 'sources': []})}\n\n"
        return

    # Headless browser screenshot (Playwright) when user asks or Chat mode is "browser"
    if _should_attempt_chat_browser_capture(message, chat_request_mode):
        target_url = _extract_page_capture_url(message)
        if not target_url and chat_request_mode == "browser":
            hint = (
                "Browser mode needs a target. Include a full URL (https://…) or a phrase like "
                "**GitHub profile SomeUser** or **github page SomeUser** so the server can open a page and attach a screenshot."
            )
            yield f"data: {json.dumps({'text': hint, 'done': True, 'sources': [], 'routing': {'primary_role': 'browser', 'reasoning': 'browser mode — missing URL'}})}\n\n"
            return
        if target_url:
            yield f"data: {json.dumps({'text': '', 'done': False, 'searching_web': True, 'search_status': 'Capturing page in headless browser…'})}\n\n"
            b64, err, final_u = await _chat_playwright_screenshot(target_url)
            yield f"data: {json.dumps({'text': '', 'done': False, 'searching_web': False, 'search_status': ''})}\n\n"
            if err:
                fail = (
                    f"I tried to open **{target_url}** in a headless browser but could not capture it: {err}\n\n"
                    "Check that Playwright is installed (`pip install playwright` then `playwright install chromium`), "
                    "that outbound HTTPS is allowed, and that the URL is reachable."
                )
                yield f"data: {json.dumps({'text': fail, 'done': True, 'sources': [], 'routing': {'primary_role': 'browser', 'reasoning': 'browser capture failed'}})}\n\n"
                return
            browser_png_b64 = b64
            browser_capture_url = final_u or target_url
            yield f"data: {json.dumps({'browser_screenshot_b64': browser_png_b64, 'browser_screenshot_url': browser_capture_url, 'done': False})}\n\n"

    # Auto-route based on message content
    from models.router import classify_message
    routing = classify_message(
        message,
        has_image=has_image or bool(image_b64) or bool(browser_png_b64),
    )

    manual_override_active = False
    if model_override and model_override in MODEL_ROUTES:
        cfg = get_model_config(model_override)
        routing.primary_model = cfg.model
        routing.primary_role = model_override
        routing.pipeline = [cfg.model]
        routing.pipeline_roles = [model_override]
        routing.is_hybrid = False
        routing.reasoning = f"Manual override: {model_override}"
        routing.detected_domains = [model_override]
        manual_override_active = True

    mode = routing.primary_role if hasattr(routing, "primary_role") else routing.primary_model

    if browser_png_b64:
        image_b64 = browser_png_b64
        vm = get_model_config("vision")
        routing.primary_model = vm.model
        routing.primary_role = "vision"
        routing.pipeline = [vm.model]
        routing.pipeline_roles = ["vision"]
        routing.is_hybrid = False
        routing.detected_domains = ["vision"]
        routing.reasoning = f"Headless browser screenshot ({browser_capture_url}) — vision model."
        mode = "vision"
        manual_override_active = False
    elif image_b64 and not manual_override_active:
        mode = "vision"
        routing.primary_role = "vision"
        routing.primary_model = get_model_config("vision").model

    # Retrieve RAG context — scoped to sources ingested in this chat/session
    session_sources = session_store.get_sources(session_id)
    rag_chunks = await vectordb.retrieve(message, n=5, sources=session_sources)
    augmented_prompt = build_rag_prompt(message, rag_chunks)
    auto_research_context = ""
    auto_research_sources: list[dict] = []
    auto_research_meta = {
        "ok": False,
        "offline": False,
        "results": 0,
        "queries": [],
        "fetched_pages": 0,
        "domain_count": 0,
    }
    requires_live_answer = _requires_live_web_answer(message)
    auto_research_attempted = (
        False if browser_png_b64 else _should_auto_web_research(message, mode)
    )
    if auto_research_attempted:
        yield f"data: {json.dumps({'text': '', 'done': False, 'searching_web': True, 'search_status': 'Searching web…'})}\n\n"
        try:
            auto_research_context, auto_research_sources, auto_research_meta = await _build_auto_web_research_context(
                message,
                limit=6,
                fetch_details=requires_live_answer,
            )
        except Exception as exc:
            logger.warning("Auto web research failed: %s", exc)
            auto_research_meta = {
                "ok": False,
                "offline": True,
                "results": 0,
                "queries": _build_web_queries(message),
                "fetched_pages": 0,
                "domain_count": 0,
            }
        yield f"data: {json.dumps({'text': '', 'done': False, 'searching_web': False, 'search_status': 'Web lookup complete'})}\n\n"
    if requires_live_answer and (not auto_research_sources):
        fallback = (
            "I could not retrieve live web results for this current-data request, so I cannot provide reliable "
            "current pricing right now. Please retry in a moment, or use Research with this query: "
            f"{message}"
        )
        routing_info = {
            "primary_model": routing.primary_model,
            "primary_role": getattr(routing, "primary_role", mode),
            "pipeline": routing.pipeline,
            "pipeline_roles": getattr(routing, "pipeline_roles", routing.pipeline),
            "is_hybrid": routing.is_hybrid,
            "confidence": routing.confidence,
            "reasoning": routing.reasoning,
            "detected_domains": routing.detected_domains,
            "speed_mode": getattr(routing, "speed_mode", "balanced"),
            "manual_override": model_override if manual_override_active else None,
            "auto_web_research_attempted": auto_research_attempted,
            "auto_web_research_ok": bool(auto_research_meta.get("ok")),
            "auto_web_research_results": int(auto_research_meta.get("results", 0)),
            "auto_web_research_offline": bool(auto_research_meta.get("offline", False)),
            "auto_web_research_queries": list(auto_research_meta.get("queries") or []),
            "auto_web_research_fetched_pages": int(auto_research_meta.get("fetched_pages", 0)),
            "auto_web_research_domain_count": int(auto_research_meta.get("domain_count", 0)),
            "auto_web_research_query_count": len(list(auto_research_meta.get("queries") or [])),
            "chat_browser_capture": bool(browser_png_b64),
            "chat_browser_url": browser_capture_url or None,
        }
        session_store.add_message(session_id, "assistant", fallback, mode)
        yield f"data: {json.dumps({'text': fallback, 'done': True, 'sources': [], 'routing': routing_info})}\n\n"
        return
    if auto_research_context:
        augmented_prompt = (
            f"{augmented_prompt}\n\n"
            f"{auto_research_context}\n"
            "Use this web context as primary evidence for current facts. Do not claim a static knowledge cutoff when web context is present. "
            "If exact data is missing, say what was found and what remains uncertain. "
            "When citing web-backed claims, reference them inline with [1], [2], etc. matching the source order."
        )
    sources = [
        {"text": c["text"][:200], "source": c["source"], "score": c["score"], "url": _source_url(c["source"])}
        for c in rag_chunks
    ]
    if auto_research_sources:
        sources = [
            {
                **row,
                "url": _source_url(str(row.get("url") or row.get("source") or "")),
            }
            for row in [*auto_research_sources, *sources][:8]
        ]

    # Get model config for this mode
    config = get_model_config(mode)
    system_prompt = config.system_prompt
    if browser_png_b64:
        system_prompt = (
            f"{system_prompt}\n\n"
            "A real headless-browser viewport screenshot of the page the user asked about is attached to this turn. "
            "Describe what you see and answer their question based on the image."
        )

    # Inject Data Science context if detected
    if any(d in ["math", "code", "data_science"] for d in routing.detected_domains):
        from config.ds_context import DATA_SCIENCE_CONTEXT, DS_CODE_STANDARDS
        system_prompt = f"{system_prompt}\n\n{DATA_SCIENCE_CONTEXT}\n\n{DS_CODE_STANDARDS}"

    # Inject style profile for writing mode
    if mode == "writing":
        profile = load_style_profile()
        system_prompt = build_style_system_prompt(profile)

    # Inject knowledge graph context
    from memory.knowledge_graph import get_context_prompt
    graph_context = await get_context_prompt(session_id)
    if graph_context:
        system_prompt = f"{system_prompt}\n\n{graph_context}"

    # Store user message in this chat's session only (history is per-chat; other chats stay saved but unused here)
    session_store.add_message(session_id, "user", message, mode)

    # Per-chat rolling summary + cross-chat bullets (file-backed) in system prompt
    sess = session_store.get_session(session_id)
    roll = str(sess.get("rolling_summary") or "").strip()
    if roll:
        system_prompt = f"{system_prompt}{chat_context.build_system_context_extension(roll)}"
    cx_block = cross_chat_memory.get_prompt_block()
    if cx_block:
        system_prompt = f"{system_prompt}\n\n{cx_block}"

    # Markdown skills from Agent Space (manual selection + optional auto-match on user message).
    try:
        from agent_space.runtime import skill_store as _agent_skill_store

        skills_for_prompt: list[dict] = []
        seen_skill_slugs: set[str] = set()
        for raw in list(skill_slugs or []):
            sid = str(raw or "").strip()
            if not sid or sid in seen_skill_slugs:
                continue
            loaded = _agent_skill_store.get_skill(sid)
            if isinstance(loaded, dict) and loaded.get("slug"):
                skills_for_prompt.append(dict(loaded))
                seen_skill_slugs.add(str(loaded.get("slug")))
        if auto_select_skills:
            for loaded in _agent_skill_store.select_for_objective(message, limit=8):
                if not isinstance(loaded, dict):
                    continue
                sid = str(loaded.get("slug") or "")
                if sid and sid not in seen_skill_slugs:
                    skills_for_prompt.append(dict(loaded))
                    seen_skill_slugs.add(sid)
        if skills_for_prompt:
            skill_ctx = _agent_skill_store.build_context(skills_for_prompt, max_chars=10000)
            if skill_ctx.strip():
                system_prompt = (
                    f"{system_prompt}\n\n## Active skills\n"
                    "Apply these reusable procedures when they improve accuracy or consistency:\n"
                    f"{skill_ctx}"
                )
    except Exception:
        logger.debug("Chat skill injection skipped", exc_info=True)

    # Strong context window: cap messages + characters; avoid duplicating the current user turn
    raw_hist = history if history else session_store.get_history(session_id)
    norm = chat_context.normalize_history_messages(raw_hist)
    norm = chat_context.strip_trailing_user_matching_message(norm, message)
    history_for_model = chat_context.apply_context_window(norm)

    routing_info = {
        "primary_model": routing.primary_model,
        "primary_role": getattr(routing, "primary_role", mode),
        "pipeline": routing.pipeline,
        "pipeline_roles": getattr(routing, "pipeline_roles", routing.pipeline),
        "is_hybrid": routing.is_hybrid,
        "confidence": routing.confidence,
        "reasoning": routing.reasoning,
        "detected_domains": routing.detected_domains,
        "speed_mode": getattr(routing, "speed_mode", "balanced"),
        "manual_override": model_override if manual_override_active else None,
        "auto_web_research_attempted": auto_research_attempted,
        "auto_web_research_ok": bool(auto_research_meta.get("ok")),
        "auto_web_research_results": int(auto_research_meta.get("results", 0)),
        "auto_web_research_offline": bool(auto_research_meta.get("offline", False)),
        "auto_web_research_queries": list(auto_research_meta.get("queries") or []),
        "auto_web_research_fetched_pages": int(auto_research_meta.get("fetched_pages", 0)),
        "auto_web_research_domain_count": int(auto_research_meta.get("domain_count", 0)),
        "auto_web_research_query_count": len(list(auto_research_meta.get("queries") or [])),
        "context_window_messages": len(history_for_model),
        "context_window_chars": sum(len(m["content"]) for m in history_for_model),
        "cross_chat_memory_active": bool(cx_block),
        "rolling_summary_active": bool(roll),
        "chat_browser_capture": bool(browser_png_b64),
        "chat_browser_url": browser_capture_url or None,
    }

    # ── Hybrid pipeline execution ──────────────────────────────────────
    pipeline_roles = getattr(routing, "pipeline_roles", routing.pipeline)
    if routing.is_hybrid and not manual_override_active:
        all_responses: list[str] = []
        for step_idx, step_role in enumerate(pipeline_roles):
            step_config = get_model_config(step_role)

            current = get_current_model()
            if current and current != step_config.model:
                await ollama_client.unload_model(current)
            set_current_model(step_config.model)

            step_prompt = augmented_prompt
            if step_idx > 0 and all_responses:
                prev = "\n".join(all_responses)
                step_prompt = (
                    f"Previous analysis:\n{prev}\n\n"
                    f"Original question: {message}\n\n"
                    f"Now provide your {step_role} perspective."
                )

            step_system = step_config.system_prompt
            if any(d in ["math", "code", "data_science"] for d in routing.detected_domains):
                from config.ds_context import DATA_SCIENCE_CONTEXT, DS_CODE_STANDARDS
                step_system = f"{step_system}\n\n{DATA_SCIENCE_CONTEXT}\n\n{DS_CODE_STANDARDS}"

            yield f"data: {json.dumps({'text': '', 'step': step_idx + 1, 'total_steps': len(pipeline_roles) + 1, 'step_model': step_config.model, 'done': False})}\n\n"

            step_parts: list[str] = []
            async for chunk in ollama_client.generate(
                model=step_config.model,
                prompt=step_prompt,
                system=step_system,
                stream=True,
                temperature=step_config.temperature,
            ):
                step_parts.append(chunk)
                yield f"data: {json.dumps({'text': chunk, 'done': False, 'model': step_config.model})}\n\n"
            all_responses.append("".join(step_parts))

        # Synthesis step via chat model
        synth_config = get_model_config("chat")
        current = get_current_model()
        if current and current != synth_config.model:
            await ollama_client.unload_model(current)
        set_current_model(synth_config.model)

        synth_prompt = (
            f"Original question: {message}\n\n"
            + "\n\n---\n\n".join(
                f"[{pipeline_roles[i]} analysis]:\n{resp}"
                for i, resp in enumerate(all_responses)
            )
            + "\n\nSynthesize these analyses into one coherent, well-structured answer."
        )

        yield f"data: {json.dumps({'text': '\\n\\n---\\n*Synthesized response:*\\n\\n', 'done': False, 'model': synth_config.model})}\n\n"

        full_response: list[str] = []
        async for chunk in ollama_client.generate(
            model=synth_config.model,
            prompt=synth_prompt,
            system="Combine the specialist analyses into a clear, unified answer.",
            stream=True,
            temperature=0.5,
        ):
            full_response.append(chunk)
            yield f"data: {json.dumps({'text': chunk, 'done': False, 'model': synth_config.model})}\n\n"

        hybrid_response = "".join(full_response)
        stale_response_corrected = False
        if requires_live_answer and auto_research_sources and _response_looks_stale_for_live_request(hybrid_response):
            hybrid_response = _build_live_source_fallback_response(auto_research_sources, message)
            stale_response_corrected = True
            yield f"data: {json.dumps({'text': '\\n\\n[Live-source correction]\\n' + hybrid_response, 'done': False, 'model': synth_config.model})}\n\n"
        session_store.add_message(session_id, "assistant", hybrid_response, mode)
        _schedule_memory_update(session_id, message, hybrid_response)
        routing_info["stale_response_corrected"] = stale_response_corrected
        yield f"data: {json.dumps({'text': '', 'done': True, 'sources': sources, 'routing': routing_info})}\n\n"
        return

    # ── Compare models: pipeline from prompt context (env overrides optional) ───
    if COMPARE_MODELS_ENABLED and not manual_override_active:
        pipe_a, pipe_b, pipe_judge = get_compare_pipeline(routing)
        role_a = COMPARE_MODEL_A_ROLE if COMPARE_MODEL_A_ROLE else pipe_a
        role_b = COMPARE_MODEL_B_ROLE if COMPARE_MODEL_B_ROLE else pipe_b
        judge_role = JUDGE_MODEL_ROLE or pipe_judge
        cfg_a = get_model_config(role_a)
        cfg_b = get_model_config(role_b)
        judge_config = get_model_config(judge_role)
        images = [image_b64] if image_b64 and mode == "vision" else None
        chat_messages_compare = ollama_client._build_chat_messages(
            history_for_model,
            augmented_prompt,
            system=system_prompt,
            images=images,
            max_history_turns=chat_context.CHAT_MAX_HISTORY_MESSAGES,
            max_total_chars=chat_context.CHAT_MAX_HISTORY_CHARS,
        )
        # Run model A (GPU) and B (NPU if OLLAMA_NPU_BASE_URL set, else GPU)
        response_a = await ollama_client.chat_full(
            cfg_a.model, chat_messages_compare, temperature=cfg_a.temperature
        )
        response_b = await ollama_client.chat_full(
            cfg_b.model, chat_messages_compare, temperature=cfg_b.temperature,
            base_url=OLLAMA_NPU_BASE_URL,
        )
        # Judge: pick or synthesize one answer
        judge_system = (
            "You are a judge. The user asked a question and two models gave answers. "
            "Pick the better answer or combine the best parts into one clear, correct response. "
            "Output only the final answer to show the user—no meta-commentary or 'Model A/B' labels."
        )
        judge_user = (
            f"User asked: {message}\n\n"
            f"Model A ({cfg_a.model}):\n{response_a}\n\n"
            f"Model B ({cfg_b.model}):\n{response_b}"
        )
        judge_messages = [{"role": "system", "content": judge_system}, {"role": "user", "content": judge_user}]
        current = get_current_model()
        if current and current != judge_config.model:
            await ollama_client.unload_model(current)
        set_current_model(judge_config.model)
        yield f"data: {json.dumps({'text': '', 'compare': True, 'model_a': cfg_a.model, 'model_b': cfg_b.model, 'done': False})}\n\n"
        full_response_list: list[str] = []
        async for chunk in ollama_client.chat_stream(
            model=judge_config.model, messages=judge_messages, stream=True, temperature=0.4
        ):
            full_response_list.append(chunk)
            yield f"data: {json.dumps({'text': chunk, 'done': False, 'model': judge_config.model})}\n\n"
        full_response_str = "".join(full_response_list)
        review_text = None
        if LAYERED_REVIEW_ENABLED:
            full_response_str, review_text = await _run_review(message, full_response_str)
        stale_response_corrected = False
        if requires_live_answer and auto_research_sources and _response_looks_stale_for_live_request(full_response_str):
            full_response_str = _build_live_source_fallback_response(auto_research_sources, message)
            stale_response_corrected = True
            yield f"data: {json.dumps({'text': '\\n\\n[Live-source correction]\\n' + full_response_str, 'done': False, 'model': judge_config.model})}\n\n"
        session_store.add_message(session_id, "assistant", full_response_str, mode)
        _schedule_memory_update(session_id, message, full_response_str)
        routing_info["compare_models"] = [cfg_a.model, cfg_b.model]
        routing_info["compare_pipeline_roles"] = [role_a, role_b, judge_role]
        routing_info["judge_model"] = judge_config.model
        routing_info["stale_response_corrected"] = stale_response_corrected
        if OLLAMA_NPU_BASE_URL:
            routing_info["npu_used_for"] = "model_b"
        yield f"data: {json.dumps({'text': '', 'done': True, 'sources': sources, 'routing': routing_info, 'review': review_text})}\n\n"
        return

    # ── Single model execution (with conversation history) ───────────────
    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    speed_mode = get_speed_mode()
    params = get_inference_params(mode, speed_mode)
    images = [image_b64] if image_b64 and mode == "vision" else None
    chat_messages = ollama_client._build_chat_messages(
        history_for_model,
        augmented_prompt,
        system=system_prompt,
        images=images,
        max_history_turns=chat_context.CHAT_MAX_HISTORY_MESSAGES,
        max_total_chars=chat_context.CHAT_MAX_HISTORY_CHARS,
    )

    consistency_meta: dict = {}
    judge_meta: Optional[dict] = None
    full_response_str: str

    # Math (non-hybrid): self-consistency sampling, then optional judge, then stream final answer
    if mode == "math" and not routing.is_hybrid:
        consistency = await self_consistent_math(message)
        full_response_str = consistency["answer"]
        consistency_meta = {
            "confidence": consistency.get("confidence", "single_shot"),
            "agreement_rate": consistency.get("agreement_rate"),
            "n_samples": consistency.get("n_samples", 1),
        }
        if should_judge(mode, speed_mode.value, len(message)):
            verdict = await judge_response(
                question=message,
                response=full_response_str,
                response_model=config.model,
                domain=mode,
            )
            if verdict and not verdict.passed and verdict.revised_response:
                full_response_str = verdict.revised_response
            judge_meta = _judge_meta(verdict) if verdict else None
        # Stream the final answer in chunks
        chunk_size = 80
        for i in range(0, len(full_response_str), chunk_size):
            chunk = full_response_str[i : i + chunk_size]
            yield f"data: {json.dumps({'text': chunk, 'done': False, 'model': config.model})}\n\n"
    else:
        # Standard single-shot generation with inference params
        full_response = []
        async for chunk in ollama_client.chat_stream(
            model=config.model,
            messages=chat_messages,
            stream=True,
            temperature=params.get("temperature", config.temperature),
            num_ctx=params.get("num_ctx"),
            repeat_penalty=params.get("repeat_penalty", 1.1),
        ):
            full_response.append(chunk)
            if not requires_live_answer:
                yield f"data: {json.dumps({'text': chunk, 'done': False, 'model': config.model})}\n\n"
        full_response_str = "".join(full_response)

        if should_judge(mode, speed_mode.value, len(message)):
            verdict = await judge_response(
                question=message,
                response=full_response_str,
                response_model=config.model,
                domain=mode,
            )
            if verdict and not verdict.passed and verdict.revised_response:
                full_response_str = verdict.revised_response
            judge_meta = _judge_meta(verdict) if verdict else None

    review_text = None
    if LAYERED_REVIEW_ENABLED:
        full_response_str, review_text = await _run_review(message, full_response_str)
    stale_response_corrected = False
    if requires_live_answer and auto_research_sources and _response_looks_stale_for_live_request(full_response_str):
        full_response_str = _build_live_source_fallback_response(auto_research_sources, message)
        stale_response_corrected = True
    if requires_live_answer:
        chunk_size = 120
        for i in range(0, len(full_response_str), chunk_size):
            chunk = full_response_str[i : i + chunk_size]
            yield f"data: {json.dumps({'text': chunk, 'done': False, 'model': config.model})}\n\n"

    session_store.add_message(session_id, "assistant", full_response_str, mode)
    _schedule_memory_update(session_id, message, full_response_str)
    routing_info["stale_response_corrected"] = stale_response_corrected

    if OLLAMA_NPU_BASE_URL and LAYERED_REVIEW_ENABLED and review_text:
        routing_info["npu_used_for"] = "review"
    yield f"data: {json.dumps({'text': '', 'done': True, 'sources': sources, 'routing': routing_info, 'review': review_text, 'consistency': consistency_meta, 'judge': judge_meta})}\n\n"


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post("")
async def chat(req: ChatRequest) -> StreamingResponse:
    """Streaming chat endpoint — returns SSE chunks."""
    return StreamingResponse(
        _stream_chat(
            req.message,
            req.mode,
            req.session_id,
            req.history,
            model_override=req.model_override,
            has_image=req.has_image,
            image_b64=req.image,
            skill_slugs=list(req.skill_slugs or []),
            auto_select_skills=bool(req.auto_select_skills),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str) -> dict:
    """Return chat history for a session."""
    messages = session_store.get_history(session_id)
    return {"session_id": session_id, "messages": messages}


@router.delete("/history/{session_id}")
async def clear_history(session_id: str) -> dict:
    """Clear chat history for a session."""
    session_store.clear_session(session_id)
    return {"session_id": session_id, "cleared": True}


# ── Persistent chat sessions ──────────────────────────────────────────

class SaveChatRequest(BaseModel):
    id: str
    title: str = ""
    messages: list[dict] = []


@router.get("/sessions")
async def list_sessions() -> list[dict]:
    """List all saved chats (metadata only)."""
    return chat_store.list_chats()


@router.get("/sessions/{chat_id}")
async def get_session(chat_id: str) -> dict:
    """Load a saved chat by ID."""
    data = chat_store.load_chat(chat_id)
    if data is None:
        return {"error": "not_found"}
    return data


@router.put("/sessions/{chat_id}")
async def save_session(chat_id: str, req: SaveChatRequest) -> dict:
    """Save or update a chat."""
    title = req.title or chat_store.generate_title(req.messages)
    return chat_store.save_chat(chat_id, title, req.messages)


@router.delete("/sessions/{chat_id}")
async def delete_session(chat_id: str) -> dict:
    """Delete a saved chat."""
    deleted = chat_store.delete_chat(chat_id)
    return {"deleted": deleted}
