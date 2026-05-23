"""Web tools API — fetch a URL, take screenshots, and summarize."""

import ipaddress
import logging
import socket
from typing import List
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from models import ollama_client
from models.router import get_current_model, set_current_model
from config.models import MODEL_ROUTES, get_speed_mode
from config.inference_params import get_inference_params
from tools import web_search
from tools import screenshot as screenshot_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/web", tags=["web"])


def _assert_public_http_url(raw: str) -> None:
    """SSRF guard: allow only http(s) to public IPs.

    Rejects non-web schemes and any host that resolves to a private, loopback,
    link-local, reserved, multicast, or unspecified address (e.g. 169.254.169.254
    cloud metadata, 127.0.0.1, 192.168.x, 10.x). Note: this validates the requested
    host; a public host that 30x-redirects to an internal one is not covered here.
    """
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http(s) URLs are allowed.")
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(status_code=400, detail="URL has no host.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        raise HTTPException(status_code=400, detail="Could not resolve host.")
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified
        ):
            raise HTTPException(
                status_code=400,
                detail="Refusing to fetch a private/internal address (SSRF guard).",
            )


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
    _assert_public_http_url(url)  # SSRF guard before any server-side fetch

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

