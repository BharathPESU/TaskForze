"""Reminder Agent — proactive WhatsApp and voice escalation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from nexus.config import settings
from nexus.tools import db_tools
from nexus.tools.retry import send_whatsapp_with_retry, start_vapi_call_with_retry
from nexus.tools.whatsapp_tools import Button

logger = structlog.get_logger(__name__)


async def run(instruction: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reminder agent steps are scheduler-compatible and idempotent."""
    logger.info("reminder_agent_run", instruction=instruction[:120])
    return await poll_and_escalate()


async def poll_and_escalate() -> dict[str, Any]:
    """Run the proactive escalation policy over the upcoming task window."""
    now = datetime.now(timezone.utc)
    upcoming_tasks = await db_tools.get_upcoming_tasks(window_minutes=130)
    actions_taken: list[dict[str, Any]] = []

    for task in upcoming_tasks:
        deadline = _parse_dt(task.get("deadline"))
        if deadline is None:
            continue

        minutes_until = (deadline - now).total_seconds() / 60
        last_reminder = await db_tools.get_last_reminder(task["id"])
        if _should_skip(last_reminder, now):
            continue

        action = {"task_id": task["id"], "title": task["title"], "minutes_until": round(minutes_until, 1)}
        number = settings.user_whatsapp_number
        if not number:
            action["status"] = "skipped"
            action["reason"] = "no_user_whatsapp_number"
            actions_taken.append(action)
            continue

        if 30 < minutes_until <= 120:
            text = (
                f"Hey {settings.user_name}, Nexus here.\n"
                f"'{task['title']}' is due in about {int(minutes_until)} minutes.\n"
                "No action needed yet, just keeping it visible."
            )
            response = await send_whatsapp_with_retry(number, text)
            await db_tools.log_reminder({"task_id": task["id"], "channel": "whatsapp", "outcome": "no_response"})
            action.update({"channel": "whatsapp", "type": "informational", "response": response})

        elif 0 < minutes_until <= 30:
            text = (
                f"Hey {settings.user_name}, Nexus here.\n"
                f"'{task['title']}' is due in {int(minutes_until)} minutes.\n"
                "Choose an action below."
            )
            response = await send_whatsapp_with_retry(
                number,
                text,
                buttons=[
                    Button(title="Done", callback_data=f"ack:{task['id']}"),
                    Button(title="Snooze 15m", callback_data=f"snooze_15:{task['id']}"),
                    Button(title="Snooze 1h", callback_data=f"snooze_60:{task['id']}"),
                ],
            )
            await db_tools.log_reminder({"task_id": task["id"], "channel": "whatsapp", "outcome": "no_response"})
            action.update({"channel": "whatsapp", "type": "button_prompt", "response": response})

        elif minutes_until <= 0 and _should_call(last_reminder, minutes_until):
            response = await start_vapi_call_with_retry(
                to=number,
                task_title=task["title"],
                task_id=task["id"],
            )
            await db_tools.log_reminder({"task_id": task["id"], "channel": "voice", "outcome": "escalated"})
            action.update({"channel": "voice", "type": "escalation", "response": response})

        if action.get("channel"):
            actions_taken.append(action)

    return {
        "agent": "reminder",
        "status": "success",
        "tasks_checked": len(upcoming_tasks),
        "actions_taken": actions_taken,
        "summary": f"Checked {len(upcoming_tasks)} deadline(s) and triggered {len(actions_taken)} reminder action(s)",
        "timestamp": now.isoformat(),
    }


def _should_skip(last_reminder: dict[str, Any] | None, now: datetime) -> bool:
    if not last_reminder:
        return False
    if last_reminder.get("outcome") == "ack":
        return True

    snooze_until = _parse_dt(last_reminder.get("snooze_until"))
    if snooze_until and snooze_until > now:
        return True

    sent_at = _parse_dt(last_reminder.get("sent_at"))
    if sent_at and (now - sent_at).total_seconds() / 60 < 25:
        return True
    return False


def _should_call(last_reminder: dict[str, Any] | None, minutes_until: float) -> bool:
    minutes_overdue = abs(minutes_until)
    if minutes_overdue < 10:
        return False
    if not last_reminder:
        return True
    return last_reminder.get("outcome") not in ("ack", "snoozed")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
