"""Check local stack and outbound web reachability for Agent Space research."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_space.paths import DATA_ROOT  # noqa: E402
from agent_space.web_research import DDG_API, WIKI_API, _qdrant, _searxng_url  # noqa: E402


async def _probe(client: httpx.AsyncClient, name: str, url: str, *, headers: dict[str, str] | None = None) -> dict:
    try:
        resp = await client.get(url, headers=headers)
        return {
            "name": name,
            "ok": resp.status_code < 500,
            "status_code": int(resp.status_code),
            "url": url,
        }
    except Exception as exc:
        return {"name": name, "ok": False, "status_code": 0, "url": url, "error": str(exc)}


async def main() -> None:
    qdrant_url, qdrant_key = _qdrant()
    probes: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        probes["searxng"] = await _probe(client, "searxng", f"{_searxng_url()}/search?q=test&format=json")
        probes["duckduckgo"] = await _probe(client, "duckduckgo", f"{DDG_API}?q=test&format=json&no_html=1&skip_disambig=1")
        probes["wikipedia"] = await _probe(client, "wikipedia", f"{WIKI_API}?action=query&list=search&srsearch=test&srlimit=1&format=json&origin=*")
        probes["google"] = await _probe(client, "google", "https://www.google.com/search?q=test")
        probes["qdrant_unauth"] = await _probe(client, "qdrant_unauth", f"{qdrant_url}/collections")
        probes["qdrant_auth"] = await _probe(
            client,
            "qdrant_auth",
            f"{qdrant_url}/collections",
            headers={"api-key": qdrant_key} if qdrant_key else None,
        )

    result = {
        "cwd": str(Path.cwd()),
        "data_root": str(DATA_ROOT),
        "secure_env_path": str(DATA_ROOT / "secure" / "free-stack.env"),
        "searxng_url": _searxng_url(),
        "qdrant_url": qdrant_url,
        "qdrant_key_configured": bool(str(qdrant_key).strip()),
        "http_proxy": os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "",
        "https_proxy": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "",
        "probes": probes,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
