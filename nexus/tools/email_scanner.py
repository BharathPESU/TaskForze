"""IMAP-based inbox polling for extracting action items."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from nexus.config import settings
from nexus.tools.gemini_tools import generate_json

logger = structlog.get_logger(__name__)

ACTION_PHRASES = [
    "please",
    "can you",
    "by friday",
    "by monday",
    "by tomorrow",
    "need you to",
    "action required",
    "following up",
    "waiting on you",
    "could you",
    "would you mind",
    "deadline",
]


class EmailScanner:
    """Background-only inbox scanner used by the comms layer."""

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    async def scan_action_items(self, window_minutes: int = 30) -> list[dict[str, Any]]:
        if not self.email or not self.password:
            logger.info("email_scanner_skipped", reason="missing_credentials")
            return []

        try:
            from imap_tools import AND, MailBox
        except Exception:
            logger.warning("email_scanner_unavailable", reason="imap_tools_missing")
            return []

        results: list[dict[str, Any]] = []
        since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        try:
            with MailBox("imap.gmail.com").login(self.email, self.password) as mailbox:
                for msg in mailbox.fetch(AND(seen=False, date_gte=since.date()), limit=50):
                    body = (msg.text or msg.html or "").lower()
                    if any(phrase in body for phrase in ACTION_PHRASES):
                        proposed_task = await self._extract_task(msg)
                        results.append(
                            {
                                "action_item": proposed_task.get("title", msg.subject or "Inbox follow-up"),
                                "from": msg.from_,
                                "deadline": proposed_task.get("deadline"),
                                "proposed_task": proposed_task,
                            }
                        )
        except Exception as exc:
            logger.warning("email_scanner_failed", error=str(exc))
            return []

        return results

    async def _extract_task(self, msg: Any) -> dict[str, Any]:
        prompt = f"""
        Extract a structured task from this email.
        From: {getattr(msg, "from_", "")}
        Subject: {getattr(msg, "subject", "")}
        Body: {(getattr(msg, "text", "") or getattr(msg, "html", "") or "")[:600]}

        Return JSON only:
        {{
          "title": "",
          "description": "",
          "deadline": "ISO timestamp or null",
          "priority": 1
        }}
        """
        try:
            return await generate_json(prompt=prompt)
        except Exception:
            return {
                "title": getattr(msg, "subject", "Inbox follow-up"),
                "description": "",
                "deadline": None,
                "priority": 3,
            }


scanner = EmailScanner(
    email=settings.gmail_address,
    password=settings.gmail_app_password,
)
