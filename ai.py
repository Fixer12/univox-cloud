"""Ask Claude to write the sketch. Uses a forced tool call so the answer is always structured."""
import os

from .prompts import FIX_TEMPLATE, SYSTEM_PROMPT, TOOL
from .samples import pick_sample

MODEL = os.getenv("AI_MODEL", "claude-haiku-4-5")
MOCK = os.getenv("MOCK_AI", "") == "1"


class AIError(Exception):
    """Message is safe to show to the user."""


def ai_ready() -> bool:
    return MOCK or bool(os.getenv("ANTHROPIC_API_KEY"))


def _client():
    from anthropic import Anthropic
    return Anthropic(timeout=60.0, max_retries=1)


def generate(request: str, previous_sketch: str = "", errors: str = "") -> dict:
    """Return dict with title, explanation, wiring, sketch."""
    if MOCK or not os.getenv("ANTHROPIC_API_KEY"):
        if not MOCK:
            raise AIError("The server has no Anthropic API key yet (ANTHROPIC_API_KEY).")
        return dict(pick_sample(request))
    if previous_sketch:
        content = FIX_TEMPLATE.format(errors=errors, sketch=previous_sketch, request=request)
    else:
        content = request
    try:
        resp = _client().messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "submit_firmware"},
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:  # noqa
        name = type(e).__name__
        if "Authentication" in name:
            raise AIError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY on the server.")
        if "RateLimit" in name:
            raise AIError("The AI is busy right now. Try again in a minute.")
        if "BadRequest" in name and "credit" in str(e).lower():
            raise AIError("The Anthropic account is out of credit.")
        if "NotFound" in name:
            raise AIError(f"The AI model name '{MODEL}' was not found. Check AI_MODEL on the server.")
        raise AIError(f"The AI service failed ({name}). Try again.")
    for block in resp.content:
        if getattr(block, "type", "") == "tool_use" and block.name == "submit_firmware":
            data = dict(block.input)
            if not isinstance(data.get("sketch"), str):
                raise AIError("The AI returned an unusable answer. Try again.")
            data.setdefault("title", "Custom program")
            data.setdefault("explanation", "")
            data.setdefault("wiring", [])
            return data
    raise AIError("The AI did not return a program. Try rephrasing the request.")
