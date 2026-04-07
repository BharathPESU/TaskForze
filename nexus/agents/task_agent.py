"""Task Agent — owns the user's work graph and ranked execution queue."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from nexus.tools import db_tools
from nexus.tools.dependency_graph import TaskDependencyGraph
from nexus.tools.gemini_tools import generate_json

logger = structlog.get_logger(__name__)

TASK_SYSTEM_PROMPT = """You are the Task Agent for Nexus. You own the user's work graph.

Responsibilities:
- Create, update, and query tasks in PostgreSQL
- Use the directed acyclic graph engine to resolve dependencies
- Rank actionable tasks by urgency x importance x effort
- Surface cognitive load warnings when the day becomes too dense
- When a task slips, identify downstream tasks that need replanning

Always return structured JSON with actionable tasks ranked by priority score.
"""


async def run(instruction: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a task workflow step."""
    logger.info("task_agent_run", instruction=instruction[:120])
    context = context or {}
    workflow_state = context.get("workflow_state")

    action = await _determine_action(instruction, context)
    tasks = await db_tools.get_tasks(limit=500)
    dependencies = await db_tools.get_all_dependencies()
    graph = TaskDependencyGraph()
    graph.load_from_db(tasks, dependencies)

    result: dict[str, Any] = {
        "agent": "task",
        "action": action["action"],
        "status": "success",
    }

    if action["action"] == "create":
        task_data = action["task_data"]
        task_data.setdefault("linked_workflow_id", workflow_state.workflow_id if workflow_state else None)
        created = await db_tools.create_task(task_data)
        result["created_task"] = created
        result["summary"] = f"Created task '{created['title']}'"

    elif action["action"] == "update" and action.get("task_id"):
        updated = await db_tools.update_task(action["task_id"], action["updates"])
        result["updated_task"] = updated
        if action["updates"].get("deadline"):
            refreshed_tasks = await db_tools.get_tasks(limit=500)
            refreshed_deps = await db_tools.get_all_dependencies()
            graph.load_from_db(refreshed_tasks, refreshed_deps)
            result["downstream_impacts"] = graph.cascade_slip(action["task_id"])
        result["summary"] = f"Updated task '{updated.get('title', action['task_id'])}'"

    elif action["action"] == "compute_load":
        date_str = action.get("date") or datetime.now(timezone.utc).date().isoformat()
        load = await db_tools.compute_daily_load(date_str)
        result["load"] = load
        result["warnings"] = ["Cognitive load exceeds 8"] if load["is_heavy"] else []
        result["summary"] = f"Cognitive load for {date_str}: {load['load_score']}"

    elif action["action"] == "upcoming":
        upcoming = await db_tools.get_upcoming_tasks(window_minutes=130)
        result["tasks"] = upcoming
        result["summary"] = f"{len(upcoming)} tasks are approaching their deadline"

    else:
        ranked = await db_tools.get_ranked_tasks(limit=20)
        actionable = await db_tools.get_actionable_tasks(limit=20)
        load = await db_tools.compute_daily_load(datetime.now(timezone.utc).date().isoformat())
        result["tasks"] = ranked
        result["actionable_tasks"] = actionable
        result["dependency_cycles_detected"] = graph.detect_cycles()
        result["load"] = load
        result["warnings"] = ["Cognitive load exceeds 8"] if load["is_heavy"] else []
        result["summary"] = f"Ranked {len(ranked)} actionable tasks for execution"

    refreshed_tasks = await db_tools.get_tasks(limit=500)
    refreshed_deps = await db_tools.get_all_dependencies()
    graph.load_from_db(refreshed_tasks, refreshed_deps)
    result["tasks"] = result.get("tasks", graph.get_ranked_tasks())
    result["dependencies"] = refreshed_deps
    result["top_task"] = result["tasks"][0] if result.get("tasks") else None
    return result


async def _determine_action(instruction: str, context: dict[str, Any]) -> dict[str, Any]:
    lowered = instruction.lower()
    if any(token in lowered for token in ["add task", "create task", "new task"]):
        return {"action": "create", "task_data": await _extract_task_data(instruction, context)}
    if "cognitive load" in lowered or "load score" in lowered:
        return {"action": "compute_load", "date": datetime.now(timezone.utc).date().isoformat()}
    if "update task" in lowered:
        return {"action": "update", "task_id": "", "updates": {}}
    if any(token in lowered for token in ["upcoming", "deadline", "due soon"]):
        return {"action": "upcoming"}

    try:
        ai_result = await generate_json(
            prompt=f"""
            Analyze this task instruction and return JSON only:
            {{
              "action": "create|update|analyze|compute_load|upcoming",
              "task_data": {{"title": "", "description": "", "priority": 3, "deadline": null, "effort_hours": 1}},
              "task_id": "",
              "updates": {{}},
              "date": null
            }}

            Instruction: {instruction}
            Context: {context}
            """,
            system_instruction=TASK_SYSTEM_PROMPT,
        )
        if not ai_result.get("action"):
            ai_result = {"action": "analyze"}
        if ai_result.get("action") == "create":
            ai_result["task_data"] = await _extract_task_data(instruction, context, ai_result.get("task_data"))
        return ai_result
    except Exception:
        return {"action": "analyze"}


async def _extract_task_data(
    instruction: str,
    context: dict[str, Any],
    seed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed = dict(seed or {})
    title = seed.get("title") or _title_from_instruction(instruction)
    deadline = seed.get("deadline") or _deadline_from_instruction(instruction)
    priority = int(seed.get("priority") or _priority_from_instruction(instruction))
    effort_hours = float(seed.get("effort_hours") or _effort_from_instruction(instruction))
    description = seed.get("description") or instruction

    dependencies = []
    dependency_text = _dependency_title_from_instruction(instruction)
    if dependency_text:
        for task in await db_tools.get_tasks(limit=100):
            if dependency_text.lower() in task["title"].lower():
                dependencies.append(task["id"])

    calendar_context = (
        context.get("workflow_state").get_agent_output("calendar") or {}
        if context.get("workflow_state")
        else {}
    )
    meeting_hours = float(calendar_context.get("meeting_hours", 0) or 0)
    load = await db_tools.compute_daily_load(datetime.now(timezone.utc).date().isoformat(), meeting_hours=meeting_hours)

    return {
        "title": title,
        "description": description,
        "priority": priority,
        "deadline": deadline,
        "effort_hours": effort_hours,
        "status": "pending",
        "dependencies": dependencies,
        "cognitive_load_score": load["avg_complexity"] or priority,
    }


def _title_from_instruction(instruction: str) -> str:
    cleaned = re.sub(r"(?i)^(add|create)\s+task:?\s*", "", instruction).strip()
    return cleaned.split(" by ")[0].split(" due ")[0].strip().rstrip(".") or "Untitled task"


def _dependency_title_from_instruction(instruction: str) -> str | None:
    match = re.search(r"depends on (.+)", instruction, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(".")
    return None


def _priority_from_instruction(instruction: str) -> int:
    lowered = instruction.lower()
    if "urgent" in lowered or "asap" in lowered:
        return 5
    if "important" in lowered:
        return 4
    return 3


def _effort_from_instruction(instruction: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(hour|hr)", instruction, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 1.0


def _deadline_from_instruction(instruction: str) -> str | None:
    lowered = instruction.lower()
    now = datetime.now(timezone.utc)

    if "tomorrow" in lowered:
        return (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat()
    if "today" in lowered:
        return now.replace(hour=17, minute=0, second=0, microsecond=0).isoformat()

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for name, weekday in weekdays.items():
        if name in lowered:
            days_ahead = (weekday - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat()

    iso_match = re.search(r"\d{4}-\d{2}-\d{2}", instruction)
    if iso_match:
        return f"{iso_match.group(0)}T17:00:00+00:00"
    return None
