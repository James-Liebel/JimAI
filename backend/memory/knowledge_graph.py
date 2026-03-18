"""Knowledge graph — extracts entities/relationships from sessions."""

import json
import logging
from pathlib import Path

from config.settings import KNOWLEDGE_GRAPH_FULL_PATH

logger = logging.getLogger(__name__)


def _load_graph() -> dict:
    """Load the knowledge graph from disk."""
    path = KNOWLEDGE_GRAPH_FULL_PATH
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"nodes": [], "edges": []}


def _save_graph(graph: dict) -> None:
    """Persist the knowledge graph to disk."""
    path = KNOWLEDGE_GRAPH_FULL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=2), encoding="utf-8")


async def update_graph(session_summary: str) -> None:
    """Extract entities from a session summary and merge into the graph."""
    from models import ollama_client

    extraction_prompt = (
        "Extract structured information from this conversation summary.\n"
        "Return a JSON object with two arrays:\n"
        '- "nodes": each with "id", "type" (topic/project/person/course), "label"\n'
        '- "edges": each with "source", "target", "relation"\n\n'
        f"Summary:\n{session_summary}\n\n"
        "Return ONLY valid JSON, no explanation."
    )

    try:
        response = await ollama_client.generate_full(
            model="qwen3:8b",
            prompt=extraction_prompt,
            temperature=0.2,
        )
        # Try to parse the JSON from the response
        # The model might wrap it in markdown code blocks
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        extracted = json.loads(text)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Could not extract graph from session: %s", exc)
        return

    graph = _load_graph()

    # Merge nodes (deduplicate by id)
    existing_ids = {n["id"] for n in graph["nodes"]}
    for node in extracted.get("nodes", []):
        if node.get("id") and node["id"] not in existing_ids:
            graph["nodes"].append(node)
            existing_ids.add(node["id"])

    # Merge edges (deduplicate by source+target+relation)
    existing_edges = {
        (e["source"], e["target"], e["relation"]) for e in graph["edges"]
    }
    for edge in extracted.get("edges", []):
        key = (edge.get("source"), edge.get("target"), edge.get("relation"))
        if all(key) and key not in existing_edges:
            graph["edges"].append(edge)
            existing_edges.add(key)

    _save_graph(graph)
    logger.info(
        "Graph updated: %d nodes, %d edges",
        len(graph["nodes"]),
        len(graph["edges"]),
    )


async def get_context_prompt(session_id: str) -> str:
    """Build a context string from the most relevant graph nodes."""
    graph = _load_graph()
    if not graph["nodes"]:
        return ""

    # Group nodes by type
    by_type: dict[str, list[str]] = {}
    for node in graph["nodes"]:
        t = node.get("type", "topic")
        by_type.setdefault(t, []).append(node.get("label", node.get("id", "")))

    parts: list[str] = ["Context from your knowledge graph:"]
    for node_type, labels in by_type.items():
        parts.append(f"  {node_type.title()}s: {', '.join(labels[:10])}")
    return "\n".join(parts)
