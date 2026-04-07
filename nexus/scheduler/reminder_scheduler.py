"""Reminder scheduler — polls deadlines every 60s via APScheduler."""

from __future__ import annotations

import asyncio
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from nexus.agents.runtime import set_agent_status
from nexus.config import settings

logger = structlog.get_logger(__name__)

scheduler = AsyncIOScheduler()


async def _reminder_job():
    """Scheduled job: poll upcoming tasks and send reminders."""
    from nexus.agents.reminder_agent import poll_and_escalate

    try:
        set_agent_status("reminder", "active", "Polling upcoming deadlines")
        result = await poll_and_escalate()
        actions = result.get("actions_taken", [])
        if actions:
            logger.info(
                "reminder_poll_complete",
                actions_count=len(actions),
                tasks_checked=result.get("tasks_checked", 0),
            )
        set_agent_status("reminder", "done", result.get("summary", "Reminder poll complete"))
    except Exception as exc:
        set_agent_status("reminder", "error", str(exc))
        logger.error("reminder_poll_error", error=str(exc))


def start_scheduler():
    """Start the APScheduler with the reminder polling job."""
    scheduler.add_job(
        _reminder_job,
        trigger=IntervalTrigger(seconds=settings.reminder_poll_seconds),
        id="reminder_poll",
        name="Reminder deadline poll",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "scheduler_started",
        interval_seconds=settings.reminder_poll_seconds,
    )


def stop_scheduler():
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
