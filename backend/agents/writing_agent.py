"""Writing agent — generates text using the user's style profile."""

import logging

from models import ollama_client
from models.router import get_current_model, set_current_model
from models.prompts import load_style_profile, build_style_system_prompt
from config.models import MODEL_ROUTES, get_speed_mode
from config.inference_params import get_inference_params

logger = logging.getLogger(__name__)


async def run(task: str) -> dict:
    """Execute a writing task with style profile injection.

    Returns {draft, word_count}.
    """
    config = MODEL_ROUTES["writing"]

    # VRAM management
    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    # Load and build style prompt
    profile = load_style_profile()
    system_prompt = build_style_system_prompt(profile)

    params = get_inference_params("writing", get_speed_mode())

    # Estimate if task requires sectioned output
    word_estimate = len(task.split()) * 10  # rough heuristic

    if word_estimate > 500:
        # Split into sections
        planning_prompt = (
            f"Plan the structure for this writing task. "
            f"List section headings only, one per line:\n\n{task}"
        )
        plan = await ollama_client.generate_full(
            model=config.model,
            prompt=planning_prompt,
            system=system_prompt,
            temperature=0.5,
            num_ctx=params.get("num_ctx"),
            num_batch=params.get("num_batch"),
            repeat_penalty=params.get("repeat_penalty", 1.15),
        )
        sections = [s.strip() for s in plan.strip().split("\n") if s.strip()]

        draft_parts: list[str] = []
        for section in sections[:10]:  # max 10 sections
            section_prompt = (
                f"You are writing a piece about: {task}\n\n"
                f"Write the section titled: {section}\n"
                f"Be thorough but concise."
            )
            part = await ollama_client.generate_full(
                model=config.model,
                prompt=section_prompt,
                system=system_prompt,
                temperature=params.get("temperature", config.temperature),
                num_ctx=params.get("num_ctx"),
                num_predict=params.get("num_predict"),
                num_batch=params.get("num_batch"),
                repeat_penalty=params.get("repeat_penalty", 1.15),
            )
            draft_parts.append(part)

        draft = "\n\n".join(draft_parts)
    else:
        draft = await ollama_client.generate_full(
            model=config.model,
            prompt=task,
            system=system_prompt,
            temperature=params.get("temperature", config.temperature),
            num_ctx=params.get("num_ctx"),
            num_predict=params.get("num_predict"),
            num_batch=params.get("num_batch"),
            repeat_penalty=params.get("repeat_penalty", 1.15),
        )

    word_count = len(draft.split())
    return {"draft": draft, "word_count": word_count}
