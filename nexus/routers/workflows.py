"""Workflow, task, note, and status endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from nexus.agents.runtime import get_agent_statuses
from nexus.memory.semantic_memory import memory
from nexus.tools import db_tools

router = APIRouter(tags=["Workflows & Tasks"])


@router.get("/workflows")
async def list_workflows() -> list[dict[str, Any]]:
    """List recent workflow runs."""
    return await db_tools.get_workflows()


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict[str, Any]:
    """Replay a specific workflow run."""
    result = await db_tools.get_workflow(workflow_id)
    if result is None:
        return {"error": "Workflow not found"}
    return result


@router.get("/agents/status")
async def agents_status() -> dict[str, Any]:
    """Return the live status of all five agents."""
    return {"agents": get_agent_statuses()}


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    priority: int = 3
    deadline: str | None = None
    effort_hours: float | None = None
    dependencies: list[str] = []


@router.get("/tasks")
async def list_tasks(status: str | None = None) -> list[dict[str, Any]]:
    """Return ranked tasks with priority scores by default."""
    if status:
        return await db_tools.get_tasks(status=status)
    return await db_tools.get_ranked_tasks()


@router.post("/tasks")
async def create_task(req: CreateTaskRequest) -> dict[str, Any]:
    """Create a task directly."""
    return await db_tools.create_task(
        {
            "title": req.title,
            "description": req.description,
            "priority": req.priority,
            "deadline": req.deadline,
            "effort_hours": req.effort_hours,
            "dependencies": req.dependencies,
        }
    )


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    """Get a single task."""
    result = await db_tools.get_task_by_id(task_id)
    if result is None:
        return {"error": "Task not found"}
    return result


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update a task's fields."""
    return await db_tools.update_task(task_id, updates)


@router.post("/tasks/{task_id}/snooze")
async def snooze_task(task_id: str, minutes: int = 30) -> dict[str, Any]:
    """Snooze a task deadline."""
    return await db_tools.snooze_task(task_id, minutes=minutes)


@router.post("/tasks/{task_id}/done")
async def mark_task_done(task_id: str) -> dict[str, Any]:
    """Mark a task done and acknowledge open reminders."""
    await db_tools.mark_acknowledged(task_id)
    return await db_tools.update_task(task_id, {"status": "done"})


@router.get("/notes/search")
async def search_notes(q: str) -> list[dict[str, Any]]:
    """Semantic note search."""
    return await memory.search(q, user_id="user_01", top_k=5)


@router.get("/load/{date}")
async def daily_load(date: str) -> dict[str, Any]:
    """Compute task load for a date."""
    return await db_tools.compute_daily_load(date)
