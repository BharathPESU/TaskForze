"""Optional Google ADK MCP tool bootstrap helpers."""

from __future__ import annotations

from contextlib import AsyncExitStack

from nexus.config import settings


async def _from_server(url: str, token: str):
    exit_stack = AsyncExitStack()
    if not url or not token:
        return [], exit_stack

    try:
        from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
    except Exception:
        return [], exit_stack

    tools, exit_stack = await MCPToolset.from_server(
        connection_params=SseServerParams(
            url=url,
            headers={"Authorization": f"Bearer {token}"},
        )
    )
    return tools, exit_stack


async def get_calendar_tools():
    return await _from_server(settings.gcal_mcp_url, settings.gcal_mcp_token)


async def get_gmail_tools():
    return await _from_server(settings.gmail_mcp_url, settings.gmail_mcp_token)

