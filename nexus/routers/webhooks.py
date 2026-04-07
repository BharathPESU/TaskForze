"""Webhook endpoints for WhatsApp Cloud API, legacy Twilio, and Vapi."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import PlainTextResponse

from nexus.agents.orchestrator import process
from nexus.middleware.security import (
    validate_vapi_webhook,
    validate_whatsapp_webhook,
    verify_whatsapp_webhook,
)
from nexus.tools import db_tools
from nexus.tools.retry import send_whatsapp_with_retry
from nexus.tools.whatsapp_tools import wa_client

router = APIRouter(prefix="/webhook", tags=["Webhooks"])
logger = structlog.get_logger(__name__)


@router.get("/whatsapp")
async def whatsapp_verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
) -> int:
    """Meta webhook verification handshake."""
    return await verify_whatsapp_webhook(hub_mode, hub_verify_token, hub_challenge)


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request) -> dict[str, Any]:
    """Handle inbound WhatsApp text messages and button replies."""
    await validate_whatsapp_webhook(request)
    payload = await request.json()
    parsed = wa_client.parse_webhook(payload)
    if not parsed:
        return {"status": "ignored"}

    if parsed.get("callback_data"):
        return await _handle_button_reply(parsed["callback_data"])

    if parsed.get("text"):
        final_result = await _process_chat_message(parsed["text"])
        await send_whatsapp_with_retry(parsed["from"], final_result["summary"][:1500])
        return {"status": "ok", "summary": final_result["summary"]}

    return {"status": "ignored"}


@router.post("/twilio")
async def twilio_webhook(
    Body: str = Form(""),
    From: str = Form(""),
) -> PlainTextResponse:
    """Legacy compatibility endpoint for existing Twilio sandbox demos."""
    logger.info("twilio_webhook", body=Body, from_=From)
    body_lower = Body.strip().lower()
    if "done" in body_lower:
        await _handle_button_reply("ack")
        return PlainTextResponse("Marked the most urgent task as done.")
    if "snooze 15" in body_lower:
        await _handle_button_reply("snooze_15")
        return PlainTextResponse("Snoozed the most urgent task for 15 minutes.")
    if "snooze 1" in body_lower or "snooze 60" in body_lower:
        await _handle_button_reply("snooze_60")
        return PlainTextResponse("Snoozed the most urgent task for 60 minutes.")

    final_result = await _process_chat_message(Body)
    return PlainTextResponse(final_result["summary"][:1500])


@router.post("/vapi")
async def vapi_webhook(request: Request) -> dict[str, Any]:
    """Handle Vapi call outcomes for done/snooze intents."""
    await validate_vapi_webhook(request)
    body = await request.json()
    logger.info("vapi_webhook", type=body.get("type"))

    transcript = (body.get("transcript") or "").lower()
    metadata = body.get("metadata", {})
    task_id = metadata.get("task_id")

    if task_id:
        if "done" in transcript or "complete" in transcript:
            await db_tools.mark_acknowledged(task_id)
            await db_tools.update_task(task_id, {"status": "done"})
        elif "snooze" in transcript:
            await db_tools.snooze_task(task_id, minutes=30)
        else:
            await db_tools.log_reminder({"task_id": task_id, "channel": "voice", "outcome": "no_response"})

    return {"status": "ok"}


async def _handle_button_reply(callback_data: str) -> dict[str, Any]:
    action, _, explicit_task_id = callback_data.partition(":")
    task = await db_tools.get_task_by_id(explicit_task_id) if explicit_task_id else None
    if task is None:
        upcoming = await db_tools.get_upcoming_tasks(window_minutes=180)
        if not upcoming:
            return {"status": "ok", "message": "No pending tasks found"}
        task = upcoming[0]

    if action == "ack":
        await db_tools.mark_acknowledged(task["id"])
        await db_tools.update_task(task["id"], {"status": "done"})
        return {"status": "ok", "message": f"Marked '{task['title']}' done"}
    if action == "snooze_15":
        result = await db_tools.snooze_task(task["id"], minutes=15)
        return {"status": "ok", "message": result["new_deadline"]}
    if action == "snooze_60":
        result = await db_tools.snooze_task(task["id"], minutes=60)
        return {"status": "ok", "message": result["new_deadline"]}
    return {"status": "ignored"}


async def _process_chat_message(message: str) -> dict[str, Any]:
    final_result: dict[str, Any] = {}
    async for event in process(message):
        if event.get("type") == "result":
            final_result = event
    return final_result or {"summary": "Nexus processed your message."}
