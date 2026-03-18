"""Upload API — file and URL ingestion into the vector store."""

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

from memory.ingest import ingest_any
from memory.session import add_source

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/upload", tags=["upload"])


class UrlRequest(BaseModel):
    url: str
    session_id: str = "default"


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = "default",
) -> dict:
    """Accept a multipart file upload, ingest it into ChromaDB."""
    # Save to a temp file preserving the extension
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    source_name = file.filename or "uploaded_file"
    try:
        text = await ingest_any(tmp_path, source_name=source_name)
        # Count chunks from vectordb
        from memory.vectordb import _chunk_text
        chunk_count = len(_chunk_text(text)) if text else 0
        add_source(session_id, source_name)
        return {
            "success": True,
            "source": source_name,
            "chunks_indexed": chunk_count,
        }
    except Exception as exc:
        logger.error("Upload failed for %s: %s", source_name, exc)
        return {"success": False, "source": source_name, "error": str(exc)}
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/url")
async def upload_url(req: UrlRequest) -> dict:
    """Fetch a URL, extract text, ingest into ChromaDB."""
    import httpx
    from bs4 import BeautifulSoup

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(req.url, follow_redirects=True)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove nav, footer, script, style
        for tag in soup(["nav", "footer", "script", "style", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)

        from memory.vectordb import ingest_document, _chunk_text

        source_name = req.url[:100]
        chunk_count = await ingest_document(text, source=source_name)
        add_source(req.session_id, source_name)
        return {
            "success": True,
            "source": source_name,
            "chunks_indexed": chunk_count,
        }
    except Exception as exc:
        logger.error("URL ingest failed for %s: %s", req.url, exc)
        return {"success": False, "source": req.url, "error": str(exc)}
