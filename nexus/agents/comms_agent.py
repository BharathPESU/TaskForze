"""Comms Agent — owns email drafts, inbox action extraction, and summaries."""

from __future__ import annotations

from typing import Any

import structlog

from nexus.memory.semantic_memory import memory
from nexus.tools import gmail_tools
from nexus.tools.email_scanner import scanner
from nexus.tools.gemini_tools import generate_json
from nexus.tools.google_auth import is_authenticated

logger = structlog.get_logger(__name__)

COMMS_SYSTEM_PROMPT = """You are the Comms Agent for Nexus. You own outbound communication.

Responsibilities:
- Scan inbox messages for action items
- Draft emails using task and note context
- Match tone to the target audience
- Never send email autonomously without approval
"""


async def run(instruction: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a communication step."""
    logger.info("comms_agent_run", instruction=instruction[:120])
    context = context or {}
    workflow_state = context.get("workflow_state")
    user_id = context.get("user_id", "user_01")
    notes_output = workflow_state.get_agent_output("notes") if workflow_state else {}
    task_output = workflow_state.get_agent_output("task") if workflow_state else {}

    action = await _determine_action(instruction)
    result: dict[str, Any] = {"agent": "comms", "action": action["action"], "status": "success"}

    if action["action"] == "scan_inbox":
        action_items = await scanner.scan_action_items(window_minutes=30)
        result["action_items"] = action_items
        result["summary"] = f"Scanned inbox and found {len(action_items)} action item(s)"
        return result

    context_notes = notes_output.get("results") or await memory.search(
        query=instruction,
        user_id=user_id,
        top_k=3,
    )
    pending_tasks = (task_output.get("tasks") or [])[:3]

    if action["action"] == "draft_email":
        draft = await _draft_email(instruction, context_notes, pending_tasks)
        result["draft"] = draft
        result["summary"] = f"Drafted email '{draft['subject']}'"
        return result

    if action["action"] == "send_email":
        draft = await _draft_email(instruction, context_notes, pending_tasks)
        draft["approval_required"] = True
        result["draft"] = draft
        result["summary"] = "Prepared an email draft, but did not send because approval is required"
        return result

    inbox_messages = []
    if is_authenticated():
        inbox = await gmail_tools.list_messages(max_results=5, query="is:unread")
        inbox_messages = inbox.get("messages", [])

    result["inbox_summary"] = {
        "messages": inbox_messages,
        "context_used": [note["id"] for note in context_notes[:3]],
        "top_pending_tasks": pending_tasks,
    }
    result["summary"] = f"Prepared a communication summary using {len(context_notes[:3])} contextual note(s)"
    return result


async def _determine_action(instruction: str) -> dict[str, Any]:
    lowered = instruction.lower()
    if any(token in lowered for token in ["scan inbox", "check inbox", "action items"]):
        return {"action": "scan_inbox"}
    if any(token in lowered for token in ["draft", "write email", "compose"]):
        return {"action": "draft_email"}
    if any(token in lowered for token in ["send email", "send this"]):
        return {"action": "send_email"}

    try:
        result = await generate_json(
            prompt=f"""
            Analyze this communication request and return JSON only:
            {{
              "action": "scan_inbox|draft_email|send_email|summarize"
            }}

            Instruction: {instruction}
            """,
            system_instruction=COMMS_SYSTEM_PROMPT,
        )
        if not result.get("action"):
            return {"action": "summarize"}
        return result
    except Exception:
        return {"action": "summarize"}


async def _draft_email(
    instruction: str,
    context_notes: list[dict[str, Any]],
    pending_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = f"""
    Draft an email for this request: {instruction}

    Context notes:
    {context_notes}

    Pending tasks:
    {pending_tasks}

    Return JSON only:
    {{
      "to": "recipient@example.com",
      "subject": "",
      "body": "",
      "tone": "professional",
      "context_used": []
    }}
    """
    try:
        draft = await generate_json(prompt=prompt, system_instruction=COMMS_SYSTEM_PROMPT)
    except Exception:
        draft = {}

    return {
        "to": draft.get("to", "recipient@example.com"),
        "subject": draft.get("subject", "Nexus follow-up"),
        "body": draft.get("body", "Hello,\n\nHere is the update from Nexus.\n"),
        "tone": draft.get("tone", "professional"),
        "context_used": draft.get("context_used", [note["id"] for note in context_notes[:3]]),
        "approval_required": True,
    }
