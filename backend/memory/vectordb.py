"""ChromaDB vector storage — ingest documents, retrieve by semantic similarity."""

import logging
import warnings
from pathlib import Path
from typing import Any

# Chroma currently emits a Python 3.14 compatibility warning via pydantic.v1.
# Suppress this specific upstream warning noise for cleaner local logs.
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
    module="chromadb.config",
)

try:
    import chromadb  # type: ignore
    _CHROMA_AVAILABLE = True
    _CHROMA_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - import-time compatibility fallback
    chromadb = None  # type: ignore
    _CHROMA_AVAILABLE = False
    _CHROMA_IMPORT_ERROR = str(exc)

from config.settings import CHROMA_FULL_PATH
from models import ollama_client

logger = logging.getLogger(__name__)

# Lazy-init the persistent client
_client: Any = None
_collection: Any = None
_CHROMA_WARNED = False

COLLECTION_NAME = "knowledge"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


def _get_collection() -> Any | None:
    """Return (and lazily create) the ChromaDB collection."""
    global _client, _collection, _CHROMA_WARNED
    if not _CHROMA_AVAILABLE:
        if not _CHROMA_WARNED:
            logger.warning("ChromaDB unavailable; vector store disabled: %s", _CHROMA_IMPORT_ERROR)
            _CHROMA_WARNED = True
        return None
    if _collection is None:
        db_path = str(CHROMA_FULL_PATH)
        Path(db_path).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=db_path)
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


async def ingest_document(
    text: str, source: str, metadata: dict | None = None
) -> int:
    """Chunk text, embed each chunk, and store in ChromaDB. Returns chunk count."""
    collection = _get_collection()
    if collection is None:
        return 0
    chunks = _chunk_text(text)
    if not chunks:
        return 0

    meta = metadata or {}
    ids: list[str] = []
    documents: list[str] = []
    embeddings: list[list[float]] = []
    metadatas: list[dict] = []

    for i, chunk in enumerate(chunks):
        chunk_id = f"{source}::{i}"
        embedding = await ollama_client.embed(chunk)
        ids.append(chunk_id)
        documents.append(chunk)
        embeddings.append(embedding)
        metadatas.append({**meta, "source": source, "chunk_index": i})

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    logger.info("Ingested %d chunks from source '%s'", len(chunks), source)
    return len(chunks)


async def retrieve(
    query: str,
    n: int = 5,
    sources: list[str] | None = None,
    where_metadata: dict | None = None,
) -> list[dict]:
    """Embed the query and return the top-n most similar chunks.

    Filter modes (combinable):
      • *sources* — restrict to chunks whose ``source`` field is in this list.
      • *where_metadata* — restrict by any other metadata field, e.g.
        ``{"user_id": "default", "kind": "chat_turn"}``. Used to pull past
        chat history regardless of the auto-generated per-turn source string.

    If neither filter is given the call returns [] — we never search the whole
    corpus blindly, since that would leak content across users.
    """
    collection = _get_collection()
    if collection is None:
        return []
    if collection.count() == 0:
        return []
    if not sources and not where_metadata:
        return []

    query_embedding = await ollama_client.embed(query)
    # Build a Chroma ``where`` filter combining source list + metadata.
    where_clauses: list[dict] = []
    if sources:
        where_clauses.append({"source": {"$in": list(sources)}})
    if where_metadata:
        for key, val in where_metadata.items():
            where_clauses.append({key: {"$eq": val}})
    if len(where_clauses) == 1:
        where_filter = where_clauses[0]
    else:
        where_filter = {"$and": where_clauses}
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n, collection.count()),
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict] = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        similarity = 1.0 - float(dist)
        # Feedback weighting: thumbs-up chunks rise, thumbs-down sink. The
        # multiplier is bounded so a single thumbs-down can't bury a chunk
        # entirely, and a single thumbs-up can't promote unrelated content.
        feedback = float((meta or {}).get("feedback_score", 0.0) or 0.0)
        # Map feedback score to a multiplier in [0.5, 1.5] using a soft curve.
        weight = max(0.5, min(1.0 + 0.1 * feedback, 1.5))
        hits.append({
            "text": doc,
            "source": (meta or {}).get("source", "unknown"),
            "score": round(similarity, 4),
            "weighted_score": round(similarity * weight, 4),
            "feedback_score": feedback,
        })
    # Re-rank by weighted score so feedback-positive chunks rise to the top
    # without losing the original similarity in the payload.
    hits.sort(key=lambda h: h.get("weighted_score", h.get("score", 0)), reverse=True)
    return hits


async def adjust_metadata(
    *,
    where: dict,
    delta_field: str,
    delta_value: float,
) -> int:
    """Atomically bump a numeric metadata field on every chunk matching ``where``.

    Used by the feedback pipeline: when a user thumbs-up's a turn, every chunk
    derived from that turn gets feedback_score += 1; thumbs-down decrements.
    Retrieval at chat time multiplies similarity scores by a feedback weight so
    well-rated material rises in the ranking.

    Returns the number of chunks updated (0 if nothing matched or the store
    is unavailable).
    """
    collection = _get_collection()
    if collection is None:
        return 0
    try:
        existing = collection.get(where=where, include=["metadatas"])
    except Exception as exc:
        logger.debug("adjust_metadata: query failed: %s", exc)
        return 0
    ids = existing.get("ids") or []
    metas = existing.get("metadatas") or []
    if not ids:
        return 0
    new_metas: list[dict] = []
    for m in metas:
        m2 = dict(m or {})
        cur = float(m2.get(delta_field, 0.0) or 0.0)
        m2[delta_field] = cur + float(delta_value)
        new_metas.append(m2)
    try:
        collection.update(ids=ids, metadatas=new_metas)
    except Exception as exc:
        logger.debug("adjust_metadata: update failed: %s", exc)
        return 0
    return len(ids)


async def delete_source(source: str) -> None:
    """Remove all chunks belonging to a source."""
    collection = _get_collection()
    if collection is None:
        return
    collection.delete(where={"source": source})
    logger.info("Deleted all chunks for source '%s'", source)


async def list_sources() -> list[str]:
    """Return unique source names in the collection."""
    collection = _get_collection()
    if collection is None:
        return []
    if collection.count() == 0:
        return []
    all_meta = collection.get(include=["metadatas"])
    sources = {m.get("source", "unknown") for m in all_meta["metadatas"]}
    return sorted(sources)
