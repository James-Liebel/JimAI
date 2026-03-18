"""Web search tool — DuckDuckGo Instant Answer API + page fetching."""

import logging

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def search(query: str, n: int = 5) -> list[dict]:
    """Search DuckDuckGo Instant Answer API (no API key needed)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_redirect": "1"},
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = []

        # Abstract (main instant answer)
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", ""),
                "snippet": data["Abstract"],
                "url": data.get("AbstractURL", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:n]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })

        return results[:n]
    except Exception as exc:
        logger.warning("Search failed: %s", exc)
        return []


async def fetch_page(url: str, max_chars: int = 8000) -> str:
    """Fetch a URL and extract main text content, stripping boilerplate."""
    try:
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove boilerplate elements
        for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
            tag.decompose()

        # Try to find main content
        main = soup.find("main") or soup.find("article") or soup.find("body")
        if main is None:
            return ""

        text = main.get_text(separator="\n", strip=True)
        return text[:max_chars]
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return f"Error fetching page: {exc}"
