"""Open-source repository discovery helpers."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

# Common OSI-approved licenses that are usually safe for free/open-source usage.
ALLOWED_LICENSE_KEYS = {
    "mit",
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "isc",
    "mpl-2.0",
    "epl-2.0",
    "agpl-3.0",
    "gpl-2.0",
    "gpl-3.0",
    "lgpl-2.1",
    "lgpl-3.0",
    "unlicense",
    "cc0-1.0",
}


def _repo_to_row(item: dict[str, Any]) -> dict[str, Any]:
    license_obj = item.get("license") if isinstance(item.get("license"), dict) else {}
    license_key = str(license_obj.get("key") or "").strip().lower()
    license_spdx = str(license_obj.get("spdx_id") or "").strip()
    free_to_use = bool(license_key and license_key in ALLOWED_LICENSE_KEYS)
    return {
        "name": str(item.get("name") or ""),
        "full_name": str(item.get("full_name") or ""),
        "url": str(item.get("html_url") or ""),
        "description": str(item.get("description") or ""),
        "stars": int(item.get("stargazers_count") or 0),
        "forks": int(item.get("forks_count") or 0),
        "language": str(item.get("language") or ""),
        "license_key": license_key,
        "license_spdx": license_spdx,
        "free_to_use": free_to_use,
        "updated_at": str(item.get("updated_at") or ""),
        "topics": list(item.get("topics") or []),
    }


async def search_open_source(
    query: str,
    *,
    limit: int = 8,
    min_stars: int = 20,
    language: str = "",
    include_unknown_license: bool = False,
) -> dict[str, Any]:
    cleaned_query = " ".join(str(query or "").strip().split())
    if not cleaned_query:
        return {"ok": False, "offline": False, "query": query, "results": [], "error": "query is required"}

    safe_limit = max(1, min(20, int(limit)))
    stars = max(0, int(min_stars))
    search_terms = [cleaned_query, f"stars:>={stars}", "archived:false", "fork:false"]
    if language.strip():
        search_terms.append(f"language:{language.strip()}")
    q = " ".join(search_terms)

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                GITHUB_SEARCH_URL,
                params={"q": q, "sort": "stars", "order": "desc", "per_page": safe_limit},
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            payload = resp.json()
        items = list(payload.get("items") or [])
        rows = [_repo_to_row(item) for item in items if isinstance(item, dict)]
        if include_unknown_license:
            filtered = [row for row in rows if row.get("free_to_use") or not row.get("license_key")]
        else:
            filtered = [row for row in rows if row.get("free_to_use")]
        return {
            "ok": True,
            "offline": False,
            "query": cleaned_query,
            "total_found": int(payload.get("total_count") or 0),
            "results": filtered[:safe_limit],
        }
    except Exception as exc:
        logger.warning("Open-source search failed: %s", exc)
        return {
            "ok": False,
            "offline": True,
            "query": cleaned_query,
            "results": [],
            "error": str(exc),
        }
