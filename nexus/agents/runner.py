"""Optional Google ADK runner helpers for future orchestration upgrades."""

from __future__ import annotations

import uuid
from typing import Any, AsyncGenerator

from nexus.config import settings

try:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
except Exception:
    Runner = None
    InMemorySessionService = None
    Content = None
    Part = None

session_service = InMemorySessionService() if InMemorySessionService else None


async def run_agent_events(
    agent: Any,
    user_message: str,
    session_id: str | None = None,
    user_id: str | None = None,
) -> AsyncGenerator[Any, None]:
    """Run an ADK agent if the dependency is available."""
    if not Runner or not session_service or not Content or not Part:
        raise RuntimeError("google-adk is not available in this environment")

    session_id = session_id or str(uuid.uuid4())
    user_id = user_id or settings.default_user_id

    await session_service.create_session(
        app_name=settings.app_name,
        user_id=user_id,
        session_id=session_id,
    )

    runner = Runner(
        agent=agent,
        app_name=settings.app_name,
        session_service=session_service,
    )
    message = Content(role="user", parts=[Part(text=user_message)])
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        yield event

