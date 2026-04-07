"""Webhook verification helpers for WhatsApp and Vapi."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request

from nexus.config import settings


async def validate_whatsapp_webhook(request: Request) -> None:
    """Validate the Meta Cloud API webhook signature when configured."""
    if not settings.whatsapp_app_secret:
        return

    signature = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()
    expected = "sha256=" + hmac.new(
        settings.whatsapp_app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid WhatsApp signature")


async def validate_vapi_webhook(request: Request) -> None:
    """Validate a Vapi webhook signature when configured."""
    if not settings.vapi_webhook_secret:
        return

    body = await request.body()
    signature = request.headers.get("x-vapi-signature", "")
    expected = hmac.new(
        settings.vapi_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid Vapi signature")


async def verify_whatsapp_webhook(mode: str, token: str, challenge: str) -> int:
    """Handle Meta's initial verification challenge."""
    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Invalid verification token")
