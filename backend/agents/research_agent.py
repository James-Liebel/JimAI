"""Research agent — searches the web, fetches pages, summarizes, and ingests."""

import logging

from models import ollama_client
from models.router import get_current_model, set_current_model
from config.models import MODEL_ROUTES
from tools import web_search
from memory import vectordb

logger = logging.getLogger(__name__)


async def run(query: str) -> dict:
    """Execute a research task: search → fetch → summarize → ingest.

    Returns {summary, sources, ingested}.
    """
    # VRAM management — research uses chat model
    config = MODEL_ROUTES["chat"]
    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    # Step 1: Search
    search_results = await web_search.search(query, n=5)
    sources = [r.get("url", "") for r in search_results if r.get("url")]

    # Step 2: Fetch top 3 pages
    page_texts: list[str] = []
    for result in search_results[:3]:
        url = result.get("url", "")
        if url:
            text = await web_search.fetch_page(url)
            if text:
                page_texts.append(f"Source: {url}\n{text[:3000]}")

    # Step 3: Summarize
    if page_texts:
        context = "\n\n---\n\n".join(page_texts)
        summary_prompt = (
            f"Summarize the following research findings about: {query}\n\n"
            f"{context}\n\n"
            "Provide a clear, well-structured summary. "
            "Cite specific sources when making claims."
        )
        summary = await ollama_client.generate_full(
            model=config.model,
            prompt=summary_prompt,
            system="You are a research assistant. Summarize findings clearly and cite sources.",
            temperature=0.5,
        )
    elif search_results:
        # Fall back to summarizing snippets
        snippets = "\n".join(
            f"- {r.get('title', '')}: {r.get('snippet', '')}"
            for r in search_results
        )
        summary = f"Search results for '{query}':\n{snippets}"
    else:
        summary = f"No results found for: {query}"

    # Step 4: Ingest summary into vector store
    ingested = False
    if summary and len(summary) > 50:
        try:
            await vectordb.ingest_document(
                summary, source=f"research:{query[:80]}"
            )
            ingested = True
        except Exception as exc:
            logger.warning("Failed to ingest research: %s", exc)

    return {
        "summary": summary,
        "sources": sources,
        "ingested": ingested,
    }
