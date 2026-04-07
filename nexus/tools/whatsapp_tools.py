"""Meta WhatsApp Cloud API wrapper with interactive reply support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from nexus.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class Button:
    title: str
    callback_data: str


class WhatsAppClient:
    BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(self, phone_id: str, token: str):
        self.phone_id = phone_id
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.phone_id and self.token)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def send_message(self, to: str, text: str) -> dict[str, Any]:
        if not self.configured:
            logger.info("whatsapp_skipped", reason="missing_credentials")
            return {"status": "skipped", "reason": "whatsapp_not_configured"}

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.phone_id}/messages",
                headers=self.headers,
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": text},
                },
            )
            response.raise_for_status()
            payload = response.json()
            logger.info("whatsapp_sent", to=to)
            return {"status": "sent", "response": payload}

    async def send_button_message(self, to: str, text: str, buttons: list[Button]) -> dict[str, Any]:
        if not self.configured:
            logger.info("whatsapp_skipped", reason="missing_credentials")
            return {"status": "skipped", "reason": "whatsapp_not_configured"}

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": button.callback_data, "title": button.title},
                        }
                        for button in buttons
                    ]
                },
            },
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.phone_id}/messages",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            logger.info("whatsapp_interactive_sent", to=to, buttons=len(buttons))
            return {"status": "sent", "response": body}

    def parse_webhook(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Extract interactive button replies or plain text from Meta payloads."""
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            message = value["messages"][0]
        except (KeyError, IndexError, TypeError):
            return None

        if message.get("type") == "interactive":
            reply = message.get("interactive", {}).get("button_reply", {})
            return {
                "from": message.get("from"),
                "callback_data": reply.get("id"),
                "title": reply.get("title"),
            }

        if message.get("type") == "text":
            return {
                "from": message.get("from"),
                "text": message.get("text", {}).get("body", ""),
            }

        return None


wa_client = WhatsAppClient(
    phone_id=settings.whatsapp_phone_id,
    token=settings.whatsapp_token,
)

