"""File type ingest handlers — extract text from various document formats."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def ingest_pdf(path: Path) -> str:
    """Extract text from PDF using pdfplumber, page by page."""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                pages.append(f"[Page {i + 1}]\n{text}")
    return "\n\n".join(pages)


async def ingest_docx(path: Path) -> str:
    """Extract text from DOCX by paragraph."""
    from docx import Document

    doc = Document(str(path))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


async def ingest_code(path: Path) -> str:
    """Read source code as-is — chunking happens at the vectordb layer."""
    return path.read_text(encoding="utf-8", errors="replace")


async def ingest_latex(path: Path) -> str:
    """Extract text from LaTeX source, preserving equations."""
    from pylatexenc.latex2text import LatexNodes2Text

    raw = path.read_text(encoding="utf-8", errors="replace")
    converter = LatexNodes2Text()
    return converter.latex_to_text(raw)


async def ingest_csv(path: Path) -> str:
    """Extract summary and first rows from CSV."""
    import pandas as pd

    try:
        df = pd.read_csv(str(path), nrows=500)
        parts = [
            f"CSV file with {df.shape[0]} rows and {df.shape[1]} columns.",
            f"Columns: {', '.join(df.columns.tolist())}",
            f"Dtypes:\n{df.dtypes.to_string()}",
            f"Summary statistics:\n{df.describe(include='all').to_string()}",
            f"First 20 rows:\n{df.head(20).to_string()}",
        ]
        return "\n\n".join(parts)
    except Exception as exc:
        logger.warning("CSV ingest failed: %s", exc)
        return path.read_text(encoding="utf-8", errors="replace")


async def ingest_notebook(path: Path) -> str:
    """Extract code and markdown cells from a Jupyter notebook."""
    import json as _json

    try:
        nb = _json.loads(path.read_text(encoding="utf-8"))
        cells = nb.get("cells", [])
        parts: list[str] = []
        for i, cell in enumerate(cells):
            cell_type = cell.get("cell_type", "unknown")
            source = "".join(cell.get("source", []))
            if source.strip():
                parts.append(f"[Cell {i + 1} ({cell_type})]:\n{source}")
        return "\n\n".join(parts)
    except Exception as exc:
        logger.warning("Notebook ingest failed: %s", exc)
        return path.read_text(encoding="utf-8", errors="replace")


async def ingest_image(path: Path) -> str:
    """Send image to the vision model for OCR / text extraction. Always returns non-empty so it gets indexed."""
    import base64
    from config.models import get_config
    from models import ollama_client

    try:
        image_bytes = path.read_bytes()
    except Exception as e:
        logger.warning("Could not read image %s: %s", path.name, e)
        return f"[Image {path.name}: file could not be read.]"

    if len(image_bytes) > 20 * 1024 * 1024:  # 20 MB
        logger.warning("Image %s too large (%d bytes), skipping vision call", path.name, len(image_bytes))
        return f"[Image {path.name}: file too large for vision model.]"

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    try:
        vision_config = get_config("vision")
        result = await ollama_client.generate_full(
            model=vision_config.model,
            prompt="Extract all text, equations, and code from this image. Be thorough and exact. If there is no text, describe the image briefly.",
            images=[b64],
            temperature=0.1,
        )
        text = (result or "").strip()
        if text:
            return text
        return f"[Image {path.name}: no text extracted; vision model returned empty.]"
    except Exception as e:
        logger.warning("Vision extraction failed for %s: %s", path.name, e)
        return f"[Image {path.name}: extraction failed - {e!s}. Ensure the vision model is pulled (e.g. ollama pull qwen2.5vl:7b) and Ollama is running.]"


async def ingest_any(path: Path, source_name: str | None = None) -> str:
    """Detect file type by extension and call the right handler."""
    from memory.vectordb import ingest_document

    ext = path.suffix.lower()
    name = source_name or path.name

    handlers = {
        ".pdf": ingest_pdf,
        ".docx": ingest_docx,
        ".doc": ingest_docx,
        ".tex": ingest_latex,
        ".csv": ingest_csv,
        ".ipynb": ingest_notebook,
        ".py": ingest_code,
        ".ts": ingest_code,
        ".tsx": ingest_code,
        ".js": ingest_code,
        ".jsx": ingest_code,
        ".md": ingest_code,
        ".txt": ingest_code,
        ".json": ingest_code,
        ".yaml": ingest_code,
        ".yml": ingest_code,
        ".toml": ingest_code,
        ".rs": ingest_code,
        ".go": ingest_code,
        ".java": ingest_code,
        ".c": ingest_code,
        ".cpp": ingest_code,
        ".h": ingest_code,
        ".xml": ingest_code,
        ".html": ingest_code,
        ".sh": ingest_code,
        ".bat": ingest_code,
        ".ps1": ingest_code,
        ".png": ingest_image,
        ".jpg": ingest_image,
        ".jpeg": ingest_image,
        ".jpe": ingest_image,
        ".webp": ingest_image,
        ".gif": ingest_image,
        ".bmp": ingest_image,
        ".heic": ingest_image,
        ".tiff": ingest_image,
        ".tif": ingest_image,
    }

    handler = handlers.get(ext)
    if handler is None:
        # Fallback: try reading as text
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            logger.warning("Cannot ingest file type '%s' for %s", ext, name)
            return ""
    else:
        text = await handler(path)

    if text:
        chunk_count = await ingest_document(text, source=name)
        logger.info("Ingested '%s' (%s) → %d chunks", name, ext, chunk_count)
    return text
