"""Google Tasks API tools — real task list operations.

Provides CRUD operations on Google Tasks via the Tasks API v1.
Falls back gracefully when no OAuth token is available.
"""

from __future__ import annotations

from typing import Any

import structlog
from googleapiclient.discovery import build

from nexus.tools.google_auth import get_google_credentials

logger = structlog.get_logger(__name__)


def _get_service():
    """Build a Tasks API service client."""
    creds = get_google_credentials()
    if not creds:
        return None
    return build("tasks", "v1", credentials=creds, cache_discovery=False)


async def list_task_lists() -> dict[str, Any]:
    """List all task lists."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated", "task_lists": []}

    try:
        result = svc.tasklists().list(maxResults=20).execute()
        lists = [
            {
                "id": tl.get("id"),
                "title": tl.get("title"),
                "updated": tl.get("updated"),
            }
            for tl in result.get("items", [])
        ]
        return {"task_lists": lists, "count": len(lists)}
    except Exception as exc:
        logger.error("tasks_list_error", error=str(exc))
        return {"error": str(exc), "task_lists": []}


async def list_tasks(
    task_list_id: str = "@default",
    show_completed: bool = False,
    max_results: int = 20,
) -> dict[str, Any]:
    """List tasks from a specific task list."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated", "tasks": []}

    try:
        result = (
            svc.tasks()
            .list(
                tasklist=task_list_id,
                maxResults=max_results,
                showCompleted=show_completed,
                showHidden=False,
            )
            .execute()
        )
        tasks = []
        for t in result.get("items", []):
            tasks.append({
                "id": t.get("id"),
                "title": t.get("title", "(No title)"),
                "notes": t.get("notes", ""),
                "due": t.get("due", ""),
                "status": t.get("status", "needsAction"),
                "updated": t.get("updated", ""),
                "parent": t.get("parent"),
                "position": t.get("position"),
            })
        logger.info("tasks_fetched", count=len(tasks))
        return {"tasks": tasks, "count": len(tasks)}

    except Exception as exc:
        logger.error("tasks_list_error", error=str(exc))
        return {"error": str(exc), "tasks": []}


async def create_task(
    title: str,
    notes: str = "",
    due: str | None = None,
    task_list_id: str = "@default",
) -> dict[str, Any]:
    """Create a new task."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated"}

    try:
        body: dict[str, Any] = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due

        created = (
            svc.tasks()
            .insert(tasklist=task_list_id, body=body)
            .execute()
        )
        logger.info("task_created", id=created.get("id"), title=title)
        return {
            "id": created.get("id"),
            "title": created.get("title"),
            "due": created.get("due"),
            "status": "created",
        }

    except Exception as exc:
        logger.error("task_create_error", error=str(exc))
        return {"error": str(exc)}


async def complete_task(
    task_id: str, task_list_id: str = "@default"
) -> dict[str, Any]:
    """Mark a task as completed."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated"}

    try:
        updated = (
            svc.tasks()
            .patch(
                tasklist=task_list_id,
                task=task_id,
                body={"status": "completed"},
            )
            .execute()
        )
        logger.info("task_completed", id=task_id)
        return {
            "id": updated.get("id"),
            "title": updated.get("title"),
            "status": "completed",
        }

    except Exception as exc:
        logger.error("task_complete_error", error=str(exc))
        return {"error": str(exc)}


async def delete_task(
    task_id: str, task_list_id: str = "@default"
) -> dict[str, Any]:
    """Delete a task."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated"}

    try:
        svc.tasks().delete(
            tasklist=task_list_id, task=task_id
        ).execute()
        logger.info("task_deleted", id=task_id)
        return {"status": "deleted", "id": task_id}

    except Exception as exc:
        logger.error("task_delete_error", error=str(exc))
        return {"error": str(exc)}
