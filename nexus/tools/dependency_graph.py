"""Task dependency engine with ranked actionable task retrieval."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


class TaskDependencyGraph:
    """Small DAG abstraction used for dependency-aware task ranking."""

    def __init__(self):
        self.tasks: dict[str, dict[str, Any]] = {}
        self._forward: dict[str, set[str]] = defaultdict(set)
        self._reverse: dict[str, set[str]] = defaultdict(set)

    def load_from_db(self, tasks: list[dict[str, Any]], dependencies: list[dict[str, Any]]) -> None:
        self.tasks = {task["id"]: dict(task) for task in tasks}
        self._forward = defaultdict(set)
        self._reverse = defaultdict(set)
        for dep in dependencies:
            self.add_dependency(dep["task_id"], dep["depends_on"])

    def add_task(self, task_id: str, **attrs: Any) -> None:
        self.tasks[task_id] = {"id": task_id, **attrs}

    def add_dependency(self, task_id: str, depends_on: str) -> None:
        self._forward[depends_on].add(task_id)
        self._reverse[task_id].add(depends_on)
        if self.detect_cycles():
            self._forward[depends_on].discard(task_id)
            self._reverse[task_id].discard(depends_on)
            raise ValueError(f"Adding dependency creates a cycle: {depends_on} -> {task_id}")

    def get_actionable_tasks(self) -> list[dict[str, Any]]:
        actionable = []
        for task_id, task in self.tasks.items():
            status = task.get("status")
            if status in ("done", "blocked"):
                continue
            if all(self.tasks.get(dep, {}).get("status") == "done" for dep in self._reverse.get(task_id, set())):
                actionable.append(dict(task))
        return actionable

    def cascade_slip(self, slipped_task_id: str) -> list[str]:
        seen: set[str] = set()
        queue = deque([slipped_task_id])
        affected: list[str] = []

        while queue:
            current = queue.popleft()
            for child in self._forward.get(current, set()):
                if child in seen:
                    continue
                seen.add(child)
                affected.append(child)
                queue.append(child)
        return affected

    def compute_priority_score(self, task_id: str) -> float:
        task = self.tasks[task_id]
        deadline = _parse_iso(task.get("deadline"))
        if deadline is None:
            urgency = 0.1
        else:
            hours_left = max((deadline - datetime.now(timezone.utc)).total_seconds() / 3600, 0.1)
            urgency = 1 / hours_left

        importance = float(task.get("priority", 3) or 3)
        effort = float(task.get("effort_hours", 1) or 1)
        return round(urgency * importance * effort, 4)

    def get_ranked_tasks(self) -> list[dict[str, Any]]:
        ranked = []
        for task in self.get_actionable_tasks():
            enriched = dict(task)
            enriched["priority_score"] = self.compute_priority_score(task["id"])
            enriched["dependencies"] = sorted(self._reverse.get(task["id"], set()))
            ranked.append(enriched)
        return sorted(ranked, key=lambda item: item["priority_score"], reverse=True)

    def detect_cycles(self) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for child in self._forward.get(node, set()):
                if walk(child):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(walk(node) for node in list(self.tasks))

    def to_json(self) -> str:
        return json.dumps(
            {
                "tasks": list(self.tasks.values()),
                "dependencies": [
                    {"task_id": task_id, "depends_on": dep}
                    for task_id, deps in self._reverse.items()
                    for dep in deps
                ],
            }
        )

    def from_json(self, data: str) -> None:
        payload = json.loads(data)
        self.load_from_db(payload.get("tasks", []), payload.get("dependencies", []))


graph = TaskDependencyGraph()

