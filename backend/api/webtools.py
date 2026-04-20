"""Web tools API — fetch a URL, take screenshots, and summarize."""

import logging
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel, HttpUrl

from models import ollama_client
from models.router import get_current_model, set_current_model
from config.models import MODEL_ROUTES, get_speed_mode
from config.inference_params import get_inference_params
from tools import web_search
from tools import screenshot as screenshot_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/web", tags=["web"])


class WebSummaryRequest(BaseModel):
    url: HttpUrl
    max_images: int = 1


class WebSummaryResponse(BaseModel):
    summary: str
    screenshots: List[str]  # base64 PNGs


@router.post("/summarize", response_model=WebSummaryResponse)
async def summarize_page(req: WebSummaryRequest) -> WebSummaryResponse:
    """Fetch a URL, take screenshots, and summarize the page content."""
    url = str(req.url)

    # 1) Fetch main text content
    page_text = await web_search.fetch_page(url)

    # 2) Capture screenshots (base64 PNG)
    screenshots_b64 = await screenshot_tool.capture_screenshots(
        url, max_images=max(1, min(req.max_images, 3))
    )

    # 3) Summarize using the chat model
    config = MODEL_ROUTES["chat"]
    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    if page_text:
        prompt = (
            f"You are given the main text content of a web page at {url}.\n\n"
            f"{page_text}\n\n"
            "Provide a concise, structured summary of this page for a human reader. "
            "Highlight the key points, any important data or arguments, and "
            "anything that seems especially relevant or unusual."
        )
    else:
        prompt = (
            f"Summarize the content of the website at {url}. "
            "The HTML text could not be extracted, so focus on describing likely "
            "purpose and contents based on typical web structure."
        )

    params = get_inference_params("chat", get_speed_mode())
    summary = await ollama_client.generate_full(
        model=config.model,
        prompt=prompt,
        system=(
            "You are a browsing assistant. Summarize web pages clearly and accurately. "
            "Assume the user can also see screenshots of the page."
        ),
        temperature=0.3,
        num_ctx=params.get("num_ctx"),
        num_predict=params.get("num_predict"),
        num_batch=params.get("num_batch"),
    )

    return WebSummaryResponse(summary=summary, screenshots=screenshots_b64)

