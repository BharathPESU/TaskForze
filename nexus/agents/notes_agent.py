"""Notes Agent — owns semantic context, memory, and reusable prep templates."""

from __future__ import annotations

from typing import Any

import structlog

from nexus.memory.semantic_memory import memory
from nexus.tools import db_tools
from nexus.tools.gemini_tools import generate_json

logger = structlog.get_logger(__name__)

NOTES_SYSTEM_PROMPT = """You are the Notes Agent for Nexus. You own the user's context and memory.

Responsibilities:
- Store notes as markdown with semantic embeddings
- Retrieve semantically relevant notes with ranked scores
- Auto-deduplicate near-identical content
- Return reusable templates for pitch prep, meeting notes, and retrospectives
"""

TEMPLATES = {
    "pitch_prep": (
        "# Pitch Prep\n\n"
        "## Objective\n- \n\n"
        "## Judges / Audience\n- \n\n"
        "## Differentiators\n- \n\n"
        "## Demo Story\n- \n"
    ),
    "meeting_notes": (
        "# Meeting Notes\n\n"
        "## Agenda\n- \n\n"
        "## Key Decisions\n- \n\n"
        "## Action Items\n- [ ] \n"
    ),
    "weekly_retro": (
        "# Weekly Retrospective\n\n"
        "## Wins\n- \n\n"
        "## Risks\n- \n\n"
        "## Next Week\n- [ ] \n"
    ),
}


async def run(instruction: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a notes workflow step against semantic memory."""
    logger.info("notes_agent_run", instruction=instruction[:120])
    context = context or {}
    user_id = context.get("user_id", "user_01")

    action = await _determine_action(instruction)
    result: dict[str, Any] = {"agent": "notes", "action": action["action"], "status": "success"}

    if action["action"] == "create":
        note_id = await memory.add(
            content=action["content"],
            user_id=user_id,
            metadata={"title": action["title"], "tags": action.get("tags", [])},
        )
        note = await db_tools.get_note(note_id)
        result["note"] = note
        result["summary"] = f"Stored note '{note.get('title', 'Untitled')}'"

    elif action["action"] == "update" and action.get("note_id"):
        await memory.update(action["note_id"], action["content"])
        updated = await db_tools.get_note(action["note_id"])
        result["note"] = updated
        result["summary"] = f"Updated note '{updated.get('title', 'Untitled')}'"

    elif action["action"] == "template":
        template_key = action.get("template_type", "meeting_notes")
        content = TEMPLATES.get(template_key, TEMPLATES["meeting_notes"])
        note_id = await memory.add(content=content, user_id=user_id, metadata={"title": template_key.replace("_", " ").title()})
        note = await db_tools.get_note(note_id)
        result["note"] = note
        result["summary"] = f"Seeded {template_key.replace('_', ' ')} template"

    else:
        query = action.get("query") or instruction
        search_results = await memory.search(query=query, user_id=user_id, top_k=5)
        result["results"] = search_results
        result["summary"] = f"Found {len(search_results)} semantically related note(s)"

    return result


async def _determine_action(instruction: str) -> dict[str, Any]:
    lowered = instruction.lower()
    if any(token in lowered for token in ["save note", "remember this", "note that"]):
        return {"action": "create", "title": "Captured Note", "content": instruction, "tags": []}
    if "template" in lowered or "meeting notes" in lowered or "retro" in lowered:
        template_type = "meeting_notes"
        if "pitch" in lowered:
            template_type = "pitch_prep"
        elif "retro" in lowered:
            template_type = "weekly_retro"
        return {"action": "template", "template_type": template_type}

    try:
        result = await generate_json(
            prompt=f"""
            Analyze this notes request and return JSON only:
            {{
              "action": "create|search|update|template",
              "title": "",
              "content": "",
              "query": "",
              "note_id": "",
              "template_type": ""
            }}

            Instruction: {instruction}
            """,
            system_instruction=NOTES_SYSTEM_PROMPT,
        )
        if not result.get("action"):
            return {"action": "search", "query": instruction}
        return result
    except Exception:
        return {"action": "search", "query": instruction}
