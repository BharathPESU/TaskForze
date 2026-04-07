"""Shared live runtime status for the Nexus agent graph."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

AGENT_TYPES = {
    "orchestrator": "primary",
    "calendar": "sub-agent",
    "task": "sub-agent",
    "notes": "sub-agent",
    "comms": "sub-agent",
    "reminder": "autonomous",
}

_lock = Lock()
_runtime: dict[str, dict[str, Any]] = {
    agent: {
        "name": agent,
        "status": "idle",
        "type": agent_type,
        "message": "Idle",
        "workflow_id": None,
        "last_update": None,
    }
    for agent, agent_type in AGENT_TYPES.items()
}


def set_agent_status(
    agent: str,
    status: str,
    message: str = "",
    workflow_id: str | None = None,
) -> None:
    """Update the status snapshot for an agent."""
    if agent not in _runtime:
        return

    with _lock:
        _runtime[agent] = {
            **_runtime[agent],
            "status": status,
            "message": message or _runtime[agent]["message"],
            "workflow_id": workflow_id,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }


def get_agent_statuses() -> list[dict[str, Any]]:
    """Return a stable list for the frontend status endpoint."""
    with _lock:
        return [dict(_runtime[name]) for name in AGENT_TYPES]

