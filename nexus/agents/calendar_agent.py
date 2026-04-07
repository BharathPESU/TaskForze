"""Calendar Agent — owns the user's time and focus blocks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from nexus.tools import calendar_tools
from nexus.tools.google_auth import is_authenticated

logger = structlog.get_logger(__name__)


async def run(instruction: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read calendar state, detect conflicts, and propose focus blocks."""
    context = context or {}
    workflow_state = context.get("workflow_state")
    logger.info("calendar_agent_run", instruction=instruction[:120])

    task_output = workflow_state.get_agent_output("task") if workflow_state else {}
    authenticated = is_authenticated()
    action = _determine_action(instruction)

    events = []
    if authenticated:
        response = await calendar_tools.list_events()
        events = response.get("events", [])

    conflicts = _find_conflicts(events)
    blocks_proposed = _propose_blocks(task_output, events)
    blocks_confirmed = []

    if action == "write" and authenticated and blocks_proposed:
        first_block = blocks_proposed[0]
        created = await calendar_tools.create_event(
            summary=first_block["summary"],
            start_time=first_block["start"],
            end_time=first_block["end"],
            description=first_block.get("description", ""),
        )
        if not created.get("error"):
            blocks_confirmed.append(created)

    meeting_hours = round(sum(_duration_hours(event) for event in events), 2)
    return {
        "agent": "calendar",
        "status": "success",
        "action": action,
        "events": events,
        "conflicts": conflicts,
        "blocks_proposed": blocks_proposed,
        "blocks_confirmed": blocks_confirmed,
        "meeting_hours": meeting_hours,
        "source": "google_calendar" if authenticated else "simulated",
        "summary": _summary(authenticated, events, blocks_proposed, conflicts),
    }


def _determine_action(instruction: str) -> str:
    lowered = instruction.lower()
    if any(token in lowered for token in ["book", "schedule it", "confirm", "write back"]):
        return "write"
    if any(token in lowered for token in ["focus", "availability", "week", "calendar", "day"]):
        return "propose"
    return "read"


def _find_conflicts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = []
    for event in events:
        start = _parse_dt(event.get("start"))
        end = _parse_dt(event.get("end"))
        if start and end:
            parsed.append((start, end, event))

    parsed.sort(key=lambda item: item[0])
    conflicts = []
    for index in range(len(parsed) - 1):
        current_end = parsed[index][1]
        next_start = parsed[index + 1][0]
        if current_end > next_start:
            conflicts.append(
                {
                    "current": parsed[index][2].get("summary", "Untitled"),
                    "next": parsed[index + 1][2].get("summary", "Untitled"),
                    "overlap_minutes": int((current_end - next_start).total_seconds() / 60),
                }
            )
    return conflicts


def _propose_blocks(task_output: dict[str, Any] | None, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks = (task_output or {}).get("tasks") or []
    duration_minutes = 90
    blocks_needed = 1
    if tasks:
        top_task = tasks[0]
        effort = float(top_task.get("effort_hours") or 1.5)
        blocks_needed = max(1, round(effort / 1.5))

    base_day = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    busy_ranges = [(_parse_dt(event.get("start")), _parse_dt(event.get("end"))) for event in events]
    busy_ranges = [(start, end) for start, end in busy_ranges if start and end]

    blocks = []
    cursor = base_day
    while len(blocks) < blocks_needed and cursor.hour < 17:
        candidate_end = cursor + timedelta(minutes=duration_minutes)
        if all(candidate_end <= busy_start or cursor >= busy_end for busy_start, busy_end in busy_ranges):
            blocks.append(
                {
                    "summary": f"Focus Block {len(blocks) + 1}",
                    "start": cursor.isoformat(),
                    "end": candidate_end.isoformat(),
                    "description": "Protected deep-work block proposed by Nexus.",
                }
            )
        cursor += timedelta(minutes=105)
    return blocks


def _duration_hours(event: dict[str, Any]) -> float:
    start = _parse_dt(event.get("start"))
    end = _parse_dt(event.get("end"))
    if not start or not end:
        return 0.0
    return max((end - start).total_seconds() / 3600, 0)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _summary(
    authenticated: bool,
    events: list[dict[str, Any]],
    blocks_proposed: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> str:
    if not authenticated:
        return f"Calendar not connected, but Nexus proposed {len(blocks_proposed)} focus block(s) in demo mode."
    return (
        f"Reviewed {len(events)} calendar event(s), detected {len(conflicts)} conflict(s), "
        f"and proposed {len(blocks_proposed)} focus block(s)."
    )
