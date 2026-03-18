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
) -> list[dict]:
    """Embed the query and return the top-n most similar chunks.

    If *sources* is provided, restrict results to chunks whose ``source``
    metadata is in that list. This lets us scope retrieval to a single
    chat/session instead of the entire corpus.
    """
    collection = _get_collection()
    if collection is None:
        return []
    if collection.count() == 0:
        return []

    query_embedding = await ollama_client.embed(query)
    if sources:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n, collection.count()),
            where={"source": {"$in": sources}},
            include=["documents", "metadatas", "distances"],
        )
    else:
        # No sources for this chat/session — return no RAG context
        return []

    hits: list[dict] = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "text": doc,
            "source": meta.get("source", "unknown"),
            "score": round(1 - dist, 4),  # cosine distance → similarity
        })
    return hits


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
