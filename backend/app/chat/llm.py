"""LiteLLM -> OpenRouter -> Cerebras call with structured output (PLAN.md §9, cerebras skill)."""

from __future__ import annotations

import asyncio
import logging

from pydantic import ValidationError

from .models import ChatResponse

log = logging.getLogger(__name__)

MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}

APOLOGY = "Sorry, I couldn't come up with a response. Please try again."


def _complete(messages: list[dict]) -> str:
    from litellm import completion  # imported lazily: litellm is slow to import

    response = completion(
        model=MODEL,
        messages=messages,
        response_format=ChatResponse,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
    )
    return response.choices[0].message.content or ""


async def call_llm(messages: list[dict]) -> str:
    """Run the blocking completion in a worker thread so the event loop keeps streaming prices."""
    return await asyncio.to_thread(_complete, messages)


def parse_response(raw: str) -> ChatResponse:
    """Validate the LLM's JSON. On failure, fall back to the raw text (or an apology) with no actions."""
    text = (raw or "").strip()
    try:
        return ChatResponse.model_validate_json(_strip_fences(text))
    except (ValidationError, ValueError) as exc:
        log.warning("LLM response failed validation: %s", exc)
        return ChatResponse(message=text or APOLOGY, trades=[], watchlist_changes=[])


def _strip_fences(text: str) -> str:
    """Tolerate a ```json ... ``` wrapper, which some models add even in structured mode."""
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()
