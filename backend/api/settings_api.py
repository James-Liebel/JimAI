"""Settings API — speed mode switching and model info."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from config.models import (
    SpeedMode, set_speed_mode, get_speed_mode, get_configs, MODEL_DISPLAY,
)
from models import ollama_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

ALL_LOADABLE_MODELS = [
    "deepseek-r1:14b",
    "qwen2.5-coder:14b",
    "qwen3:8b",
    "qwen2.5vl:7b",
    "qwen2-math:7b-instruct",
    "qwen2.5-coder:7b",
    "qwen2.5:32b",
]


class SpeedModeRequest(BaseModel):
    mode: str


@router.get("/speed-mode")
async def get_current_speed_mode():
    mode = get_speed_mode()
    configs = get_configs()
    return {
        "mode": mode.value,
        "models": {
            role: {
                "model": cfg.model,
                "display": MODEL_DISPLAY.get(cfg.model, {}),
            }
            for role, cfg in configs.items()
            if role != "embed"
        },
    }


@router.post("/speed-mode")
async def update_speed_mode(req: SpeedModeRequest):
    try:
        mode = SpeedMode(req.mode)
    except ValueError:
        return {"error": "Invalid mode. Must be: fast, balanced, or deep"}

    old_mode = get_speed_mode()
    warning = None

    if mode == SpeedMode.DEEP:
        logger.info("Switching to DEEP mode — unloading all models first")
        await ollama_client.prepare_for_deep_mode()
        warning = (
            "Deep mode loads qwen2.5:32b (~20GB VRAM). "
            "Other models unloaded. Responses will be slower but more thorough."
        )

    if old_mode == SpeedMode.DEEP and mode != SpeedMode.DEEP:
        logger.info("Leaving DEEP mode — unloading 32B model")
        try:
            await ollama_client.unload_model("qwen2.5:32b")
        except Exception:
            pass

    set_speed_mode(mode)

    configs = get_configs()
    return {
        "mode": mode.value,
        "warning": warning,
        "models": {
            role: cfg.model
            for role, cfg in configs.items()
            if role != "embed"
        },
    }
