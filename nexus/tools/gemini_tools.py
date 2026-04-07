"""Gemini AI utilities — LLM calls + embeddings via google-genai.

When GOOGLE_API_KEY is absent, returns simulated demo responses so the
app runs out of the box for UI development and hackathon demos.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from nexus.config import settings

logger = structlog.get_logger(__name__)

_client = None
_HAS_KEY = bool(settings.google_api_key)


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=settings.google_api_key)
    return _client


def _candidate_models() -> list[str]:
    models = [
        settings.gemini_model,
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
    ]
    seen = set()
    ordered = []
    for model in models:
        if model and model not in seen:
            seen.add(model)
            ordered.append(model)
    return ordered


def _candidate_embedding_models() -> list[str]:
    models = [
        settings.embedding_model,
        "gemini-embedding-001",
        "text-embedding-004",
    ]
    seen = set()
    ordered = []
    for model in models:
        if model and model not in seen:
            seen.add(model)
            ordered.append(model)
    return ordered


# ── Demo fallback responses ──────────────────────────────────────────

def _demo_plan(prompt: str) -> dict[str, Any]:
    """Generate a plausible demo execution plan."""
    return {
        "intent": prompt[:100],
        "plan": [
            {"step": 1, "agent": "calendar", "instruction": f"Check schedule for: {prompt[:60]}", "depends_on": []},
            {"step": 2, "agent": "task", "instruction": f"Create/update tasks: {prompt[:60]}", "depends_on": [1]},
            {"step": 3, "agent": "notes", "instruction": f"Save notes related to: {prompt[:60]}", "depends_on": []},
        ],
        "parallel_groups": [[1, 3], [2]],
    }


def _demo_summary() -> dict[str, Any]:
    return {
        "summary": (
            "### ✅ Workflow Complete\n\n"
            "I've processed your request across multiple agents:\n\n"
            "- **Calendar**: Checked your schedule — no conflicts found\n"
            "- **Tasks**: Updated your task list with priorities\n"
            "- **Notes**: Saved a reference note\n\n"
            "💡 *Connect your Gemini API key in `.env` for full AI-powered responses.*"
        ),
        "key_actions": ["Review task priorities", "Check calendar for this week"],
        "warnings": ["Running in demo mode — set GOOGLE_API_KEY for full functionality"],
        "follow_up_suggestions": ["Show my tasks", "What's on my calendar?"],
    }


def _demo_agent_response(instruction: str) -> dict[str, Any]:
    return {
        "summary": f"Processed: {instruction[:80]}",
        "status": "completed",
        "demo_mode": True,
    }


# ── Main functions ───────────────────────────────────────────────────

async def generate(
    prompt: str,
    system_instruction: str = "",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> str:
    """Generate text with the configured Gemini Flash model."""
    if not _HAS_KEY:
        logger.info("gemini_demo_mode", prompt_len=len(prompt))
        return json.dumps(_demo_summary())

    try:
        from google.genai import types

        client = _get_client()
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system_instruction:
            config.system_instruction = system_instruction
        if json_mode:
            config.response_mime_type = "application/json"

        last_error = None
        for model_name in _candidate_models():
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=20,
                )
                return response.text or ""
            except Exception as exc:
                last_error = exc
                logger.warning("gemini_model_attempt_failed", model=model_name, error=str(exc))
                continue

        raise last_error or RuntimeError("No Gemini model candidates succeeded")

    except Exception as exc:
        logger.error("gemini_generate_failed", error=str(exc))
        return json.dumps({"error": str(exc)})


async def generate_json(
    prompt: str,
    system_instruction: str = "",
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Generate structured JSON from Gemini."""
    if not _HAS_KEY:
        # Check if this is a plan request or summary request
        if "execution plan" in prompt.lower() or "decompose" in prompt.lower():
            return _demo_plan(prompt)
        if "summarize" in prompt.lower() or "summary" in prompt.lower():
            return _demo_summary()
        return _demo_agent_response(prompt)

    text = await generate(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=temperature,
        json_mode=True,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
            return json.loads(text)
        lowered = prompt.lower()
        if "execution plan" in lowered or "decompose" in lowered:
            return _demo_plan(prompt)
        if "summarize" in lowered or "summary" in lowered:
            return _demo_summary()
        return _demo_agent_response(prompt)


async def embed_text(text: str) -> list[float]:
    """Generate embedding vector using the configured embedding model."""
    if not _HAS_KEY:
        logger.info("embedding_demo_mode")
        return [0.0] * 768

    try:
        from google.genai import types

        client = _get_client()
        last_error = None
        for model_name in _candidate_embedding_models():
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.embed_content,
                        model=model_name,
                        contents=text,
                        config=types.EmbedContentConfig(output_dimensionality=768),
                    ),
                    timeout=15,
                )
                return list(response.embeddings[0].values)
            except Exception as exc:
                last_error = exc
                logger.warning("embedding_model_attempt_failed", model=model_name, error=str(exc))
                continue
        raise last_error or RuntimeError("No embedding model candidates succeeded")
    except Exception as exc:
        logger.error("embedding_failed", error=str(exc))
        return [0.0] * 768
