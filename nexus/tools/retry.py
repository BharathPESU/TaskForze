"""Retry helpers for external service calls."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

from nexus.tools.vapi_tools import start_call
from nexus.tools.whatsapp_tools import Button, wa_client

T = TypeVar("T")


async def _run_with_retry(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    attempts: int = 3,
    initial_delay: float = 1.0,
    retry_for: tuple[type[BaseException], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    delay = initial_delay
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except retry_for as exc:
            last_error = exc
            if attempt == attempts:
                raise
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)

    if last_error:
        raise last_error
    raise RuntimeError("Retry runner failed unexpectedly")


async def call_gemini_with_retry(fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
    return await _run_with_retry(fn, *args, retry_for=(Exception,), **kwargs)


async def send_whatsapp_with_retry(
    to: str,
    text: str,
    buttons: list[Button] | None = None,
) -> dict[str, Any]:
    if buttons:
        return await _run_with_retry(
            wa_client.send_button_message,
            to,
            text,
            buttons,
            retry_for=(httpx.HTTPError, RuntimeError),
        )
    return await _run_with_retry(
        wa_client.send_message,
        to,
        text,
        retry_for=(httpx.HTTPError, RuntimeError),
    )


async def start_vapi_call_with_retry(**kwargs: Any) -> dict[str, Any]:
    return await _run_with_retry(
        start_call,
        retry_for=(httpx.HTTPError, RuntimeError),
        **kwargs,
    )

