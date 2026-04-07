"""Database tool functions for tasks, notes, workflows, and reminders."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, select, text, update

from nexus.config import settings
from nexus.db.engine import async_session_factory
from nexus.db.models import (
    ActiveWorkflow,
    Note,
    ReminderLog,
    Task,
    TaskDependency,
    WorkflowRun,
)
from nexus.tools.dependency_graph import TaskDependencyGraph

_is_sqlite = settings.database_url.startswith("sqlite")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_uuid(value: str | uuid.UUID) -> str | uuid.UUID:
    if _is_sqlite:
        return str(value)
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _json_or_value(value: Any) -> Any:
    if _is_sqlite and isinstance(value, (list, dict)):
        return value
    return value


async def create_task(data: dict[str, Any]) -> dict[str, Any]:
    """Create a task and optionally register dependency edges."""
    async with async_session_factory() as session:
        task = Task(
            id=str(uuid.uuid4()) if _is_sqlite else uuid.uuid4(),
            title=data["title"],
            description=data.get("description", ""),
            priority=int(data.get("priority", 3) or 3),
            deadline=_parse_datetime(data.get("deadline")),
            effort_hours=data.get("effort_hours"),
            status=data.get("status", "pending"),
            cognitive_load_score=data.get("cognitive_load_score"),
            linked_workflow_id=_normalize_uuid(data["linked_workflow_id"])
            if data.get("linked_workflow_id")
            else None,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

    dependencies = data.get("dependencies") or []
    for dep_id in dependencies:
        await add_dependency(str(task.id), str(dep_id))

    return await get_task_by_id(str(task.id)) or _serialize_task(task)


async def update_task(task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update fields on an existing task."""
    payload = dict(updates)
    if "deadline" in payload:
        payload["deadline"] = _parse_datetime(payload.get("deadline"))
    if "linked_workflow_id" in payload and payload["linked_workflow_id"]:
        payload["linked_workflow_id"] = _normalize_uuid(payload["linked_workflow_id"])

    async with async_session_factory() as session:
        uid = _normalize_uuid(task_id)
        await session.execute(
            update(Task)
            .where(Task.id == uid)
            .values(**payload, updated_at=_utcnow())
        )
        await session.commit()

    result = await get_task_by_id(task_id)
    if result is None:
        return {"error": f"Task {task_id} not found"}
    return result


async def get_tasks(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve tasks with optional status filtering."""
    async with async_session_factory() as session:
        stmt = select(Task).order_by(Task.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Task.status == status)
        result = await session.execute(stmt)
        return [_serialize_task(task) for task in result.scalars().all()]


async def get_task_by_id(task_id: str) -> dict[str, Any] | None:
    async with async_session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == _normalize_uuid(task_id)))
        task = result.scalar_one_or_none()
        return _serialize_task(task) if task else None


async def get_upcoming_tasks(window_minutes: int = 130) -> list[dict[str, Any]]:
    """Get incomplete tasks due soon, including slightly overdue ones."""
    async with async_session_factory() as session:
        now = _utcnow()
        cutoff = now + timedelta(minutes=window_minutes)
        stmt = (
            select(Task)
            .where(
                and_(
                    Task.deadline.is_not(None),
                    Task.deadline <= cutoff,
                    Task.deadline >= now - timedelta(minutes=15),
                    Task.status.in_(["pending", "in_progress"]),
                )
            )
            .order_by(Task.deadline.asc())
        )
        result = await session.execute(stmt)
        return [_serialize_task(task) for task in result.scalars().all()]


async def compute_daily_load(date_str: str, meeting_hours: float = 0.0) -> dict[str, Any]:
    """Compute the task-focused cognitive load for a given UTC day."""
    target = _parse_datetime(f"{date_str}T00:00:00+00:00")
    if target is None:
        target = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    start = target
    end = start + timedelta(days=1)

    async with async_session_factory() as session:
        stmt = select(Task).where(
            and_(
                Task.deadline.is_not(None),
                Task.deadline >= start,
                Task.deadline < end,
                Task.status.in_(["pending", "in_progress"]),
            )
        )
        result = await session.execute(stmt)
        tasks = result.scalars().all()

    task_count = len(tasks)
    avg_complexity = round(
        (
            sum(task.cognitive_load_score or max(task.priority, 1) for task in tasks) / task_count
            if task_count
            else 0.0
        ),
        2,
    )
    load_score = round((meeting_hours * 1.5) + (task_count * 0.5) + avg_complexity, 2)
    return {
        "date": start.date().isoformat(),
        "meeting_hours": meeting_hours,
        "task_count": task_count,
        "avg_complexity": avg_complexity,
        "load_score": load_score,
        "is_heavy": load_score > 8,
    }


async def get_all_dependencies() -> list[dict[str, str]]:
    async with async_session_factory() as session:
        result = await session.execute(select(TaskDependency))
        return [
            {"task_id": str(dep.task_id), "depends_on": str(dep.depends_on)}
            for dep in result.scalars().all()
        ]


async def add_dependency(task_id: str, depends_on_id: str) -> dict[str, str]:
    """Add a dependency edge after validating the graph remains acyclic."""
    tasks = await get_tasks(limit=500)
    dependencies = await get_all_dependencies()
    if any(dep["task_id"] == task_id and dep["depends_on"] == depends_on_id for dep in dependencies):
        return {"task_id": task_id, "depends_on": depends_on_id}
    graph = TaskDependencyGraph()
    graph.load_from_db(tasks, dependencies)
    if task_id not in graph.tasks:
        task = await get_task_by_id(task_id)
        if task:
            graph.add_task(task_id, **task)
    graph.add_dependency(task_id, depends_on_id)

    async with async_session_factory() as session:
        session.add(
            TaskDependency(
                task_id=_normalize_uuid(task_id),
                depends_on=_normalize_uuid(depends_on_id),
            )
        )
        await session.commit()

    return {"task_id": task_id, "depends_on": depends_on_id}


async def get_dependency_graph(task_id: str | None = None) -> list[dict[str, str]]:
    async with async_session_factory() as session:
        stmt = select(TaskDependency)
        if task_id:
            stmt = stmt.where(TaskDependency.task_id == _normalize_uuid(task_id))
        result = await session.execute(stmt)
        return [
            {"task_id": str(dep.task_id), "depends_on": str(dep.depends_on)}
            for dep in result.scalars().all()
        ]


async def get_actionable_tasks(limit: int = 20) -> list[dict[str, Any]]:
    tasks = await get_tasks(limit=500)
    dependencies = await get_all_dependencies()
    graph = TaskDependencyGraph()
    graph.load_from_db(tasks, dependencies)
    return graph.get_actionable_tasks()[:limit]


async def get_ranked_tasks(limit: int = 20) -> list[dict[str, Any]]:
    tasks = await get_tasks(limit=500)
    dependencies = await get_all_dependencies()
    graph = TaskDependencyGraph()
    graph.load_from_db(tasks, dependencies)
    return graph.get_ranked_tasks()[:limit]


async def create_note(data: dict[str, Any]) -> dict[str, Any]:
    async with async_session_factory() as session:
        note = Note(
            id=str(uuid.uuid4()) if _is_sqlite else uuid.uuid4(),
            title=data.get("title", ""),
            content=data["content"],
            tags=_json_or_value(data.get("tags", [])),
            linked_task_id=_normalize_uuid(data["linked_task_id"]) if data.get("linked_task_id") else None,
            linked_event_id=data.get("linked_event_id"),
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)
        return _serialize_note(note)


async def update_note(note_id: str, content: str) -> dict[str, Any]:
    async with async_session_factory() as session:
        await session.execute(
            update(Note)
            .where(Note.id == _normalize_uuid(note_id))
            .values(content=content)
        )
        await session.commit()
        return {"id": note_id, "updated": True}


async def get_note(note_id: str) -> dict[str, Any] | None:
    async with async_session_factory() as session:
        result = await session.execute(select(Note).where(Note.id == _normalize_uuid(note_id)))
        note = result.scalar_one_or_none()
        return _serialize_note(note) if note else None


async def semantic_search(query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    """Perform vector similarity search when available."""
    if _is_sqlite:
        async with async_session_factory() as session:
            result = await session.execute(select(Note).order_by(Note.created_at.desc()).limit(top_k))
            return [
                {
                    "id": str(note.id),
                    "title": note.title,
                    "content": note.content,
                    "tags": note.tags or [],
                    "created_at": note.created_at.isoformat() if note.created_at else None,
                    "similarity": 0.0,
                }
                for note in result.scalars().all()
            ]

    embedding_str = f"[{','.join(str(v) for v in query_embedding)}]"
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT id, title, content, tags, created_at,
                       1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                FROM notes
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:emb AS vector)
                LIMIT :k
                """
            ),
            {"emb": embedding_str, "k": top_k},
        )
        rows = result.fetchall()
        return [
            {
                "id": str(row[0]),
                "title": row[1],
                "content": row[2],
                "tags": row[3] or [],
                "created_at": row[4].isoformat() if row[4] else None,
                "similarity": round(float(row[5]), 4),
            }
            for row in rows
        ]


async def set_note_embedding(note_id: str, embedding: list[float]) -> None:
    if _is_sqlite:
        async with async_session_factory() as session:
            await session.execute(
                update(Note)
                .where(Note.id == _normalize_uuid(note_id))
                .values(embedding=json.dumps(embedding))
            )
            await session.commit()
        return

    embedding_str = f"[{','.join(str(v) for v in embedding)}]"
    async with async_session_factory() as session:
        await session.execute(
            text("UPDATE notes SET embedding = CAST(:emb AS vector) WHERE id = :note_id"),
            {"emb": embedding_str, "note_id": _normalize_uuid(note_id)},
        )
        await session.commit()


async def create_workflow(
    intent: str,
    plan: list[dict[str, Any]],
    workflow_id: str | None = None,
    context: dict[str, Any] | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    async with async_session_factory() as session:
        workflow = WorkflowRun(
            id=_normalize_uuid(workflow_id or str(uuid.uuid4())),
            user_intent=intent,
            plan=plan,
            context=context or {},
            agent_outputs={},
            trace=trace or [],
            status="running",
        )
        session.add(workflow)
        await session.commit()
        await session.refresh(workflow)
        return _serialize_workflow(workflow)


async def update_workflow(
    workflow_id: str,
    agent_outputs: dict[str, Any] | None = None,
    status: str | None = None,
    context: dict[str, Any] | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if agent_outputs is not None:
        values["agent_outputs"] = agent_outputs
    if context is not None:
        values["context"] = context
    if trace is not None:
        values["trace"] = trace
    if status is not None:
        values["status"] = status
        if status in ("completed", "failed"):
            values["completed_at"] = _utcnow()

    async with async_session_factory() as session:
        await session.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == _normalize_uuid(workflow_id))
            .values(**values)
        )
        await session.commit()
    return {"id": workflow_id, "updated": True}


async def get_workflows(limit: int = 20) -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(limit)
        )
        return [_serialize_workflow(workflow) for workflow in result.scalars().all()]


async def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(WorkflowRun).where(WorkflowRun.id == _normalize_uuid(workflow_id))
        )
        workflow = result.scalar_one_or_none()
        return _serialize_workflow(workflow) if workflow else None


async def upsert_active_workflow(user_id: str, workflow_id: str) -> dict[str, Any]:
    async with async_session_factory() as session:
        existing = await session.execute(select(ActiveWorkflow).where(ActiveWorkflow.user_id == user_id))
        row = existing.scalar_one_or_none()
        if row is None:
            session.add(
                ActiveWorkflow(
                    user_id=user_id,
                    workflow_id=_normalize_uuid(workflow_id),
                )
            )
        else:
            row.workflow_id = _normalize_uuid(workflow_id)
            row.started_at = _utcnow()
        await session.commit()
        return {"user_id": user_id, "workflow_id": workflow_id}


async def get_active_workflow(user_id: str) -> dict[str, Any] | None:
    async with async_session_factory() as session:
        result = await session.execute(select(ActiveWorkflow).where(ActiveWorkflow.user_id == user_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "user_id": row.user_id,
            "workflow_id": str(row.workflow_id),
            "started_at": row.started_at.isoformat() if row.started_at else None,
        }


async def clear_active_workflow(user_id: str) -> None:
    async with async_session_factory() as session:
        await session.execute(delete(ActiveWorkflow).where(ActiveWorkflow.user_id == user_id))
        await session.commit()


async def log_reminder(data: dict[str, Any]) -> dict[str, Any]:
    async with async_session_factory() as session:
        reminder = ReminderLog(
            id=str(uuid.uuid4()) if _is_sqlite else uuid.uuid4(),
            task_id=_normalize_uuid(data["task_id"]),
            channel=data["channel"],
            sent_at=_parse_datetime(data.get("sent_at")) or _utcnow(),
            acknowledged_at=_parse_datetime(data.get("acknowledged_at")),
            outcome=data.get("outcome"),
            snooze_until=_parse_datetime(data.get("snooze_until")),
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return {
            "id": str(reminder.id),
            "task_id": str(reminder.task_id),
            "channel": reminder.channel,
            "sent_at": reminder.sent_at.isoformat() if reminder.sent_at else None,
            "acknowledged_at": reminder.acknowledged_at.isoformat() if reminder.acknowledged_at else None,
            "outcome": reminder.outcome,
            "snooze_until": reminder.snooze_until.isoformat() if reminder.snooze_until else None,
        }


async def mark_acknowledged(task_id: str) -> dict[str, Any]:
    async with async_session_factory() as session:
        await session.execute(
            update(ReminderLog)
            .where(
                and_(
                    ReminderLog.task_id == _normalize_uuid(task_id),
                    ReminderLog.acknowledged_at.is_(None),
                )
            )
            .values(acknowledged_at=_utcnow(), outcome="ack")
        )
        await session.commit()
        return {"task_id": task_id, "acknowledged": True}


async def snooze_task(task_id: str, minutes: int = 30) -> dict[str, Any]:
    snooze_until = _utcnow() + timedelta(minutes=minutes)
    async with async_session_factory() as session:
        await session.execute(
            update(ReminderLog)
            .where(
                and_(
                    ReminderLog.task_id == _normalize_uuid(task_id),
                    ReminderLog.acknowledged_at.is_(None),
                )
            )
            .values(
                acknowledged_at=_utcnow(),
                outcome="snoozed",
                snooze_until=snooze_until,
            )
        )
        await session.execute(
            update(Task)
            .where(Task.id == _normalize_uuid(task_id))
            .values(deadline=snooze_until, updated_at=_utcnow())
        )
        await session.commit()

    return {
        "task_id": task_id,
        "snoozed": True,
        "new_deadline": snooze_until.isoformat(),
    }


async def get_last_reminder(task_id: str) -> dict[str, Any] | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ReminderLog)
            .where(ReminderLog.task_id == _normalize_uuid(task_id))
            .order_by(ReminderLog.sent_at.desc())
            .limit(1)
        )
        reminder = result.scalar_one_or_none()
        if reminder is None:
            return None
        return {
            "id": str(reminder.id),
            "task_id": str(reminder.task_id),
            "channel": reminder.channel,
            "sent_at": reminder.sent_at.isoformat() if reminder.sent_at else None,
            "acknowledged_at": reminder.acknowledged_at.isoformat() if reminder.acknowledged_at else None,
            "outcome": reminder.outcome,
            "snooze_until": reminder.snooze_until.isoformat() if reminder.snooze_until else None,
        }


def _serialize_task(task: Task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "effort_hours": task.effort_hours,
        "status": task.status,
        "cognitive_load_score": task.cognitive_load_score,
        "linked_workflow_id": str(task.linked_workflow_id) if task.linked_workflow_id else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _serialize_note(note: Note) -> dict[str, Any]:
    return {
        "id": str(note.id),
        "title": note.title,
        "content": note.content,
        "tags": note.tags or [],
        "linked_task_id": str(note.linked_task_id) if note.linked_task_id else None,
        "linked_event_id": note.linked_event_id,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


def _serialize_workflow(workflow: WorkflowRun) -> dict[str, Any]:
    return {
        "id": str(workflow.id),
        "user_intent": workflow.user_intent,
        "plan": workflow.plan or [],
        "context": workflow.context or {},
        "agent_outputs": workflow.agent_outputs or {},
        "trace": workflow.trace or [],
        "status": workflow.status,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
    }
