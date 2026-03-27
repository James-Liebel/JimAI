"""Desktop screenshot helpers for the system agent."""

from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path

from config.models import get_config
from models import ollama_client

try:
    import mss
    import mss.tools
except ImportError:  # pragma: no cover - dependency guard
    mss = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - dependency guard
    Image = None


def take_screenshot(
    monitor: int = 1,
    save_path: str | None = None,
    return_base64: bool = True,
) -> dict:
    """Capture the requested monitor and optionally return PNG bytes as base64."""
    if mss is None:
        raise ImportError("mss is not installed. Run pip install mss.")

    with mss.mss() as sct:
        monitor_info = sct.monitors[monitor]
        screenshot = sct.grab(monitor_info)

        if Image is not None:
            image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            png_bytes = buffer.getvalue()
        else:
            png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)

    result = {
        "width": screenshot.size[0],
        "height": screenshot.size[1],
        "monitor": monitor,
        "timestamp": datetime.now().isoformat(),
    }

    if save_path:
        output_path = Path(save_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(png_bytes)
        result["saved_to"] = str(output_path)

    if return_base64:
        result["base64"] = base64.b64encode(png_bytes).decode("utf-8")
        result["media_type"] = "image/png"

    return result


async def screenshot_and_analyze(
    question: str = "What is on the screen? Describe everything you see.",
    monitor: int = 1,
) -> dict:
    """Capture the screen and send it through the existing local vision route."""
    screenshot = take_screenshot(monitor=monitor, return_base64=True)
    config = get_config("vision")

    analysis = ""
    async for chunk in ollama_client.generate(
        model=config.model,
        prompt=question,
        system=config.system_prompt,
        images=[screenshot["base64"]],
        stream=True,
    ):
        analysis += chunk

    return {
        "analysis": analysis,
        "screenshot": {
            "width": screenshot["width"],
            "height": screenshot["height"],
            "timestamp": screenshot["timestamp"],
        },
    }
