"""Vision API — image analysis via qwen2.5vl:7b."""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models import ollama_client
from models.router import get_current_model, set_current_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vision", tags=["vision"])


class VisionRequest(BaseModel):
    image: str  # base64 encoded
    prompt: str = "Describe this image in detail."


async def _stream_vision(
    image_b64: str, prompt: str
) -> AsyncGenerator[str, None]:
    """Stream vision model response as SSE."""
    # VRAM management
    current = get_current_model()
    if current and current != "qwen2.5vl:7b":
        await ollama_client.unload_model(current)
    set_current_model("qwen2.5vl:7b")

    system = (
        "Analyze the image carefully and completely. "
        "If it contains math or equations, extract them exactly in LaTeX. "
        "If it contains code, extract it exactly. "
        "If it contains text, transcribe it accurately. "
        "Describe layout and structure when relevant."
    )

    async for chunk in ollama_client.generate(
        model="qwen2.5vl:7b",
        prompt=prompt,
        system=system,
        stream=True,
        images=[image_b64],
        temperature=0.3,
    ):
        yield f"data: {json.dumps({'text': chunk, 'done': False})}\n\n"

    yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"


@router.post("")
async def vision(req: VisionRequest) -> StreamingResponse:
    """Analyze an image using the vision model."""
    return StreamingResponse(
        _stream_vision(req.image, req.prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
