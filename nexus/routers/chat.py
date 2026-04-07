"""Chat endpoint — POST /chat → SSE stream of agent reasoning + final response."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from nexus.agents.orchestrator import process
from nexus.config import settings

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    """User chat message."""
    message: str
    stream: bool = True
    user_id: str = settings.default_user_id


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """Process a user message through the multi-agent orchestrator.

    Returns an SSE stream of agent reasoning trace events followed
    by the final synthesized result.
    """

    async def event_stream():
        async for event in process(req.message, user_id=req.user_id):
            event_type = event.get("type", "trace")
            data = json.dumps(event, default=str)
            yield f"event: {event_type}\ndata: {data}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/stream")
async def chat_stream(message: str, user_id: str = settings.default_user_id) -> StreamingResponse:
    """GET-friendly SSE endpoint for EventSource clients."""

    async def event_stream():
        async for event in process(message, user_id=user_id):
            event_type = event.get("type", "trace")
            data = json.dumps(event, default=str)
            yield f"event: {event_type}\ndata: {data}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/sync")
async def chat_sync(req: ChatRequest) -> dict[str, Any]:
    """Non-streaming version — collects all events and returns the final result."""
    events: list[dict[str, Any]] = []
    result: dict[str, Any] = {}

    async for event in process(req.message, user_id=req.user_id):
        events.append(event)
        if event.get("type") == "result":
            result = event

    return {
        "result": result,
        "trace": [e for e in events if e.get("type") == "trace"],
    }
