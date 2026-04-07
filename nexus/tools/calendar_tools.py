"""Google Calendar API tools — real read/write operations.

Provides CRUD operations on the user's Google Calendar via the
Calendar API v3. Falls back to Gemini simulation when no OAuth
token is available.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from googleapiclient.discovery import build

from nexus.tools.google_auth import get_google_credentials

logger = structlog.get_logger(__name__)


def _get_service():
    """Build a Calendar API service client."""
    creds = get_google_credentials()
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


async def list_events(
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 15,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """List events from the user's calendar."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated", "events": []}

    now = datetime.now(timezone.utc)
    if not time_min:
        time_min = now.isoformat()
    if not time_max:
        time_max = (now + timedelta(days=7)).isoformat()

    try:
        result = (
            svc.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = []
        for ev in result.get("items", []):
            start = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date", ""))
            end = ev.get("end", {}).get("dateTime", ev.get("end", {}).get("date", ""))
            events.append({
                "id": ev.get("id"),
                "summary": ev.get("summary", "(No title)"),
                "start": start,
                "end": end,
                "location": ev.get("location", ""),
                "description": ev.get("description", ""),
                "status": ev.get("status", "confirmed"),
                "attendees": [
                    a.get("email") for a in ev.get("attendees", [])
                ],
            })
        logger.info("calendar_events_fetched", count=len(events))
        return {"events": events, "count": len(events)}

    except Exception as exc:
        logger.error("calendar_list_error", error=str(exc))
        return {"error": str(exc), "events": []}


async def create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Create a new calendar event."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated"}

    event_body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
    }
    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendees:
        event_body["attendees"] = [{"email": e} for e in attendees]

    try:
        created = svc.events().insert(
            calendarId=calendar_id, body=event_body
        ).execute()
        logger.info("calendar_event_created", id=created.get("id"))
        return {
            "id": created.get("id"),
            "summary": created.get("summary"),
            "start": created.get("start", {}).get("dateTime"),
            "end": created.get("end", {}).get("dateTime"),
            "link": created.get("htmlLink"),
            "status": "created",
        }
    except Exception as exc:
        logger.error("calendar_create_error", error=str(exc))
        return {"error": str(exc)}


async def delete_event(
    event_id: str, calendar_id: str = "primary"
) -> dict[str, Any]:
    """Delete a calendar event."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated"}

    try:
        svc.events().delete(
            calendarId=calendar_id, eventId=event_id
        ).execute()
        logger.info("calendar_event_deleted", id=event_id)
        return {"status": "deleted", "id": event_id}
    except Exception as exc:
        logger.error("calendar_delete_error", error=str(exc))
        return {"error": str(exc)}


async def find_free_slots(
    date: str | None = None,
    duration_minutes: int = 60,
) -> dict[str, Any]:
    """Find free time slots on a given day."""
    now = datetime.now(timezone.utc)
    if date:
        day_start = datetime.fromisoformat(date).replace(
            hour=9, minute=0, tzinfo=timezone.utc
        )
    else:
        day_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now.hour >= 9:
            day_start = now

    day_end = day_start.replace(hour=18, minute=0)
    events_result = await list_events(
        time_min=day_start.isoformat(),
        time_max=day_end.isoformat(),
        max_results=50,
    )

    busy_slots = []
    for ev in events_result.get("events", []):
        try:
            s = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(ev["end"].replace("Z", "+00:00"))
            busy_slots.append((s, e))
        except (ValueError, KeyError):
            continue

    busy_slots.sort(key=lambda x: x[0])

    free_slots = []
    cursor = day_start
    for busy_start, busy_end in busy_slots:
        if (busy_start - cursor).total_seconds() >= duration_minutes * 60:
            free_slots.append({
                "start": cursor.isoformat(),
                "end": busy_start.isoformat(),
                "duration_minutes": int((busy_start - cursor).total_seconds() / 60),
            })
        cursor = max(cursor, busy_end)

    if (day_end - cursor).total_seconds() >= duration_minutes * 60:
        free_slots.append({
            "start": cursor.isoformat(),
            "end": day_end.isoformat(),
            "duration_minutes": int((day_end - cursor).total_seconds() / 60),
        })

    return {"free_slots": free_slots, "count": len(free_slots)}
