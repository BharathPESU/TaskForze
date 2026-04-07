"""Orchestrator Agent — coordinates the Nexus multi-agent workflow."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import structlog

from nexus.agents import calendar_agent, comms_agent, notes_agent, reminder_agent, task_agent
from nexus.agents.runtime import set_agent_status
from nexus.config import settings
from nexus.memory.workflow_state import WorkflowState, close_workflow, get_or_create_workflow
from nexus.tools import db_tools
from nexus.tools.gemini_tools import generate_json

logger = structlog.get_logger(__name__)

ORCHESTRATOR_SYSTEM_PROMPT = """You are Nexus, the orchestrator of a multi-agent personal AI system.

Your job:
1. Understand the user's intent fully before acting.
2. Decompose the intent into a multi-step execution plan.
3. Assign each step to the correct sub-agent using the workflow state.
4. Read other agents' outputs from shared state instead of re-explaining them.
5. Handle failures by replanning and continuing where possible.
6. After completion, summarize what was done and what the user should know.

Dependency rules:
- Calendar availability needed -> Calendar Agent runs first
- Comms Agent needs task context -> Task Agent runs first
- Comms Agent needs history -> Notes Agent runs first
- Reminder Agent always runs last after tasks are confirmed
"""

AGENT_MAP = {
    "calendar": calendar_agent,
    "task": task_agent,
    "notes": notes_agent,
    "comms": comms_agent,
    "reminder": reminder_agent,
}


async def process(
    user_message: str,
    user_id: str = settings.default_user_id,
) -> AsyncGenerator[dict[str, Any], None]:
    """Process a user message and stream trace events for the dashboard."""
    workflow = get_or_create_workflow(user_id, user_message)
    workflow.context["user_id"] = user_id
    workflow.context["latest_intent"] = user_message

    set_agent_status("orchestrator", "active", "Decomposing intent", workflow.workflow_id)
    yield _trace(workflow, "orchestrator", "start", "Decomposing intent")

    plan_payload = await _build_plan(user_message)
    workflow.plan = []
    for raw_step in plan_payload["plan"]:
        workflow.add_plan_step(
            step=raw_step["step"],
            agent=raw_step["agent"],
            instruction=raw_step["instruction"],
            depends_on=raw_step.get("depends_on", []),
        )

    workflow.context["parallel_groups"] = _execution_groups(workflow.plan)
    await _persist_workflow(workflow, create=True)

    yield _trace(
        workflow,
        "orchestrator",
        "progress",
        f"Execution plan ready with {len(workflow.plan)} steps",
        {"plan": workflow.plan},
    )

    step_results: dict[int, Any] = {}
    try:
        for group in workflow.context["parallel_groups"]:
            tasks = []
            for step_id in group:
                step = next((item for item in workflow.plan if item["step"] == step_id), None)
                if not step:
                    continue

                set_agent_status(
                    step["agent"],
                    "active",
                    step["instruction"],
                    workflow.workflow_id,
                )
                workflow.update_step(step["agent"], "running")
                yield _trace(
                    workflow,
                    step["agent"],
                    "start",
                    step["instruction"],
                    {"step": step["step"]},
                )
                tasks.append(_execute_step(workflow, step, step_results))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for outcome in results:
                if isinstance(outcome, Exception):
                    logger.error("workflow_step_failed", error=str(outcome))
                    continue

                step = outcome["step"]
                agent = outcome["agent"]
                result = outcome["result"]
                step_results[step["step"]] = result
                if result.get("status") == "error":
                    workflow.update_step(agent, "error", result)
                    set_agent_status(agent, "error", result.get("error", "Agent failed"), workflow.workflow_id)
                    yield _trace(
                        workflow,
                        agent,
                        "error",
                        result.get("error", "Agent failed"),
                        {"step": step["step"]},
                    )
                else:
                    workflow.update_step(agent, "done", result)
                    set_agent_status(agent, "done", result.get("summary", "Completed"), workflow.workflow_id)
                    yield _trace(
                        workflow,
                        agent,
                        "done",
                        result.get("summary", "Completed"),
                        {"step": step["step"], "output": result},
                    )

            await _persist_workflow(workflow)

        summary = await _summarize(workflow, user_message)
        workflow.status = "completed"
        set_agent_status("orchestrator", "done", "Workflow complete", workflow.workflow_id)
        yield _trace(workflow, "orchestrator", "done", "Workflow complete")

        await _persist_workflow(workflow, status="completed")
        yield {
            "type": "result",
            "workflow_id": workflow.workflow_id,
            "summary": summary["summary"],
            "key_actions": summary["key_actions"],
            "warnings": summary["warnings"],
            "follow_up_suggestions": summary["follow_up_suggestions"],
            "workflow": workflow.to_json(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        workflow.status = "failed"
        set_agent_status("orchestrator", "error", str(exc), workflow.workflow_id)
        yield _trace(workflow, "orchestrator", "error", str(exc))
        await _persist_workflow(workflow, status="failed")
        yield {
            "type": "result",
            "workflow_id": workflow.workflow_id,
            "summary": "The workflow hit an issue, but partial results were captured.",
            "key_actions": [],
            "warnings": [str(exc)],
            "follow_up_suggestions": ["Retry the workflow", "Inspect the trace panel"],
            "workflow": workflow.to_json(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        close_workflow(user_id)
        await db_tools.clear_active_workflow(user_id)


async def _build_plan(user_message: str) -> dict[str, Any]:
    lowered = user_message.lower()
    requested = []

    if any(keyword in lowered for keyword in ["week", "today", "day", "schedule", "calendar"]):
        requested.append("calendar")
    if any(keyword in lowered for keyword in ["task", "deadline", "due", "priority", "work"]):
        requested.append("task")
    if any(keyword in lowered for keyword in ["note", "context", "prep", "remember", "history"]):
        requested.append("notes")
    if any(keyword in lowered for keyword in ["email", "inbox", "follow up", "draft", "message"]):
        requested.append("comms")
    if any(keyword in lowered for keyword in ["remind", "nudge", "deadline", "ignore", "snooze"]):
        requested.append("reminder")
    if not requested or any(keyword in lowered for keyword in ["set me up", "plan my week", "weekly"]):
        requested = ["calendar", "task", "notes", "comms", "reminder"]
    if "comms" in requested:
        if "notes" not in requested:
            requested.append("notes")
        if "task" not in requested:
            requested.append("task")
    if "reminder" in requested and "task" not in requested:
        requested.append("task")

    try:
        ai_plan = await generate_json(
            prompt=f"""
            User message: {user_message}

            Build a plan using these candidate agents: {requested}.
            Return JSON only:
            {{
              "plan": [
                {{"step": 1, "agent": "calendar", "instruction": "", "depends_on": []}}
              ]
            }}
            """,
            system_instruction=ORCHESTRATOR_SYSTEM_PROMPT,
        )
        raw_steps = ai_plan.get("plan", [])
    except Exception:
        raw_steps = []

    steps = _normalize_plan(raw_steps, user_message, requested)
    return {"plan": steps}


def _normalize_plan(
    raw_steps: list[dict[str, Any]],
    user_message: str,
    requested_agents: list[str],
) -> list[dict[str, Any]]:
    preferred_order = ["notes", "calendar", "task", "comms", "reminder"]
    present = [agent for agent in preferred_order if agent in requested_agents]

    generated = []
    for index, agent in enumerate(present, start=1):
        instruction = _default_instruction(agent, user_message)
        depends_on: list[int] = []
        if agent == "task" and "calendar" in present:
            depends_on = [present.index("calendar") + 1]
        if agent == "comms":
            depends_on = []
            if "notes" in present:
                depends_on.append(present.index("notes") + 1)
            if "task" in present:
                depends_on.append(present.index("task") + 1)
        if agent == "reminder" and "task" in present:
            depends_on = [present.index("task") + 1]
        generated.append(
            {
                "step": index,
                "agent": agent,
                "instruction": instruction,
                "depends_on": depends_on,
            }
        )

    for step in raw_steps:
        if step.get("agent") not in AGENT_MAP:
            continue
        match = next((item for item in generated if item["agent"] == step["agent"]), None)
        if match and step.get("instruction"):
            match["instruction"] = step["instruction"]

    return generated


def _default_instruction(agent: str, user_message: str) -> str:
    instructions = {
        "calendar": f"Review calendar availability and propose focus blocks for: {user_message}",
        "task": f"Rank and create actionable tasks for: {user_message}",
        "notes": f"Retrieve or save contextual notes relevant to: {user_message}",
        "comms": f"Draft or summarize communications needed for: {user_message}",
        "reminder": f"Sync reminder coverage for tasks related to: {user_message}",
    }
    return instructions[agent]


def _execution_groups(plan: list[dict[str, Any]]) -> list[list[int]]:
    level_for_step: dict[int, int] = {}
    by_level: defaultdict[int, list[int]] = defaultdict(list)

    for step in plan:
        deps = step.get("depends_on", [])
        level = 0 if not deps else max(level_for_step.get(dep, 0) for dep in deps) + 1
        level_for_step[step["step"]] = level
        by_level[level].append(step["step"])

    return [by_level[level] for level in sorted(by_level)]


async def _execute_step(
    workflow: WorkflowState,
    step: dict[str, Any],
    step_results: dict[int, Any],
) -> dict[str, Any]:
    agent_name = step["agent"]
    agent_module = AGENT_MAP[agent_name]
    context = {
        "workflow_state": workflow,
        "user_id": workflow.user_id,
        "workflow_id": workflow.workflow_id,
        "step": step,
        "previous_results": {str(dep): step_results.get(dep, {}) for dep in step.get("depends_on", [])},
    }
    result = await agent_module.run(step["instruction"], context)
    return {"agent": agent_name, "step": step, "result": result}


async def _persist_workflow(
    workflow: WorkflowState,
    create: bool = False,
    status: str | None = None,
) -> None:
    await db_tools.upsert_active_workflow(workflow.user_id, workflow.workflow_id)
    if create:
        try:
            await db_tools.create_workflow(
                intent=workflow.user_intent,
                plan=workflow.plan,
                workflow_id=workflow.workflow_id,
                context=workflow.context,
                trace=workflow.trace,
            )
        except Exception:
            await db_tools.update_workflow(
                workflow.workflow_id,
                agent_outputs=workflow.agent_outputs,
                context=workflow.context,
                trace=workflow.trace,
                status=status,
            )
        return

    await db_tools.update_workflow(
        workflow.workflow_id,
        agent_outputs=workflow.agent_outputs,
        context=workflow.context,
        trace=workflow.trace,
        status=status,
    )


async def _summarize(workflow: WorkflowState, user_message: str) -> dict[str, Any]:
    completed = []
    warnings = []
    for agent, output in workflow.agent_outputs.items():
        if output.get("status") == "error":
            warnings.append(f"{agent}: {output.get('error', 'failed')}")
        else:
            completed.append(f"{agent.title()}: {output.get('summary', 'Completed')}")

    if not completed:
        completed.append("No agent completed successfully.")

    try:
        ai_summary = await generate_json(
            prompt=json.dumps(
                {
                    "user_message": user_message,
                    "workflow": workflow.to_json(),
                },
                default=str,
            ),
            system_instruction="Summarize the workflow in JSON with summary, key_actions, warnings, follow_up_suggestions.",
        )
        if ai_summary.get("summary"):
            return {
                "summary": ai_summary.get("summary"),
                "key_actions": ai_summary.get("key_actions", []),
                "warnings": ai_summary.get("warnings", warnings),
                "follow_up_suggestions": ai_summary.get("follow_up_suggestions", []),
            }
    except Exception:
        pass

    return {
        "summary": "### Workflow Complete\n\n" + "\n".join(f"- {item}" for item in completed),
        "key_actions": [item.split(":")[0] for item in completed[:3]],
        "warnings": warnings,
        "follow_up_suggestions": ["Ask Nexus for your day plan", "Review the ranked task list"],
    }


def _trace(
    workflow: WorkflowState,
    agent: str,
    status: str,
    message: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workflow.add_trace(agent, status, message, meta)
    return {
        "type": "trace",
        "agent": agent,
        "status": status,
        "message": message,
        "workflow_id": workflow.workflow_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "meta": meta or {},
    }
