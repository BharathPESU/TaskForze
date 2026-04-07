"""Shared live workflow state passed across Nexus agents."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any


class WorkflowState:
    """Mutable workflow memory shared by all agents during execution."""

    def __init__(self, user_intent: str, user_id: str):
        self.workflow_id = str(uuid.uuid4())
        self.user_id = user_id
        self.user_intent = user_intent
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.plan: list[dict[str, Any]] = []
        self.context: dict[str, Any] = {}
        self.agent_outputs: dict[str, Any] = {}
        self.trace: list[dict[str, Any]] = []
        self.status = "running"

    def add_plan_step(
        self,
        step: int,
        agent: str,
        instruction: str,
        depends_on: list[int] | None = None,
    ) -> None:
        self.plan.append(
            {
                "step": step,
                "agent": agent,
                "instruction": instruction,
                "depends_on": depends_on or [],
                "status": "pending",
            }
        )
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def update_step(self, agent: str, status: str, output: Any = None) -> None:
        for step in self.plan:
            if step["agent"] == agent and step["status"] != "done":
                step["status"] = status

        if output is not None:
            self.agent_outputs[agent] = output

        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_trace(
        self,
        agent: str,
        status: str,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.trace.append(
            {
                "agent": agent,
                "status": status,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "meta": meta or {},
            }
        )
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_agent_output(self, agent: str) -> Any:
        return self.agent_outputs.get(agent)

    def to_json(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "user_intent": self.user_intent,
            "plan": self.plan,
            "context": self.context,
            "agent_outputs": self.agent_outputs,
            "trace": self.trace,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


_workflow_lock = Lock()
active_workflows: dict[str, WorkflowState] = {}


def get_or_create_workflow(user_id: str, intent: str) -> WorkflowState:
    """Return the current workflow for a user or start a fresh one."""
    with _workflow_lock:
        existing = active_workflows.get(user_id)
        if existing and existing.status == "running":
            existing.context.setdefault("merged_intents", []).append(intent)
            existing.context["merged_intent"] = intent
            existing.updated_at = datetime.now(timezone.utc).isoformat()
            return existing

        state = WorkflowState(intent, user_id=user_id)
        active_workflows[user_id] = state
        return state


def close_workflow(user_id: str) -> None:
    """Remove a completed workflow from the in-memory guard."""
    with _workflow_lock:
        active_workflows.pop(user_id, None)

