"""Gmail API tools — real inbox scanning and email sending.

Provides read/send operations on the user's Gmail via the
Gmail API v1. Falls back gracefully when no OAuth token is available.
"""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

import structlog
from googleapiclient.discovery import build

from nexus.tools.google_auth import get_google_credentials

logger = structlog.get_logger(__name__)


def _get_service():
    """Build a Gmail API service client."""
    creds = get_google_credentials()
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


async def list_messages(
    max_results: int = 10,
    query: str = "is:unread",
    label_ids: list[str] | None = None,
) -> dict[str, Any]:
    """List messages from the user's inbox."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated", "messages": []}

    try:
        params: dict[str, Any] = {
            "userId": "me",
            "maxResults": max_results,
            "q": query,
        }
        if label_ids:
            params["labelIds"] = label_ids

        result = svc.users().messages().list(**params).execute()
        message_ids = result.get("messages", [])

        messages = []
        for msg_ref in message_ids[:max_results]:
            msg = (
                svc.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata")
                .execute()
            )
            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
                if h["name"] in ("From", "Subject", "Date", "To")
            }
            messages.append({
                "id": msg["id"],
                "thread_id": msg.get("threadId"),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", "(No subject)"),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "labels": msg.get("labelIds", []),
            })

        logger.info("gmail_messages_fetched", count=len(messages))
        return {"messages": messages, "count": len(messages)}

    except Exception as exc:
        logger.error("gmail_list_error", error=str(exc))
        return {"error": str(exc), "messages": []}


async def get_message(message_id: str) -> dict[str, Any]:
    """Get full message content by ID."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated"}

    try:
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        headers = {
            h["name"]: h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }

        # Extract body
        body = ""
        payload = msg.get("payload", {})
        if payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="replace")
        elif payload.get("parts"):
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(
                        part["body"]["data"]
                    ).decode("utf-8", errors="replace")
                    break

        return {
            "id": msg["id"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body[:3000],
            "labels": msg.get("labelIds", []),
        }

    except Exception as exc:
        logger.error("gmail_get_error", error=str(exc))
        return {"error": str(exc)}


async def send_email(
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Send an email."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated"}

    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        sent = (
            svc.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        logger.info("gmail_sent", id=sent.get("id"), to=to)
        return {
            "id": sent.get("id"),
            "thread_id": sent.get("threadId"),
            "to": to,
            "subject": subject,
            "status": "sent",
        }

    except Exception as exc:
        logger.error("gmail_send_error", error=str(exc))
        return {"error": str(exc)}


async def get_profile() -> dict[str, Any]:
    """Get the authenticated user's email profile."""
    svc = _get_service()
    if not svc:
        return {"error": "not_authenticated"}

    try:
        profile = svc.users().getProfile(userId="me").execute()
        return {
            "email": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal"),
            "threads_total": profile.get("threadsTotal"),
        }
    except Exception as exc:
        logger.error("gmail_profile_error", error=str(exc))
        return {"error": str(exc)}
