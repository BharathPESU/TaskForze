"""Vapi.ai voice call integration — conversational AI escalation."""

from __future__ import annotations

import structlog
import httpx

from nexus.config import settings

logger = structlog.get_logger(__name__)

VAPI_BASE_URL = "https://api.vapi.ai"


async def start_call(
    to: str | None = None,
    task_title: str = "",
    task_id: str = "",
    script: str | None = None,
) -> dict[str, str]:
    """Start an outbound Vapi.ai voice call for deadline escalation.

    Args:
        to: Phone number (defaults to user's WhatsApp number).
        task_title: The task name to speak.
        task_id: Task ID for webhook correlation.
    """
    to = to or settings.user_whatsapp_number
    if not to or not settings.vapi_api_key:
        logger.warning("vapi_not_configured")
        return {"status": "skipped", "reason": "Vapi not configured"}

    # Strip 'whatsapp:' prefix if present
    phone = to.replace("whatsapp:", "")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{VAPI_BASE_URL}/call/phone",
                headers={
                    "Authorization": f"Bearer {settings.vapi_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "assistantId": None,  # Use inline assistant
                    "assistant": {
                        "model": {
                            "provider": "google",
                            "model": settings.gemini_model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": script
                                    or (
                                        f"You are Nexus, the user's AI assistant calling about an overdue task. "
                                        f"The task is: '{task_title}'. "
                                        f"Be concise and friendly. Tell them the task is overdue. "
                                        f"Ask if they want to: 1) mark it done, 2) snooze it 30 minutes, "
                                        f"or 3) update you on the status."
                                    ),
                                }
                            ],
                        },
                        "voice": {
                            "provider": "11labs",
                            "voiceId": "21m00Tcm4TlvDq8ikWAM",
                        },
                        "firstMessage": (
                            f"Hi {settings.user_name}, this is your Nexus assistant calling. "
                            f"You have a task due now: {task_title}. "
                            f"Say 'done' to mark it complete, 'snooze' to push it 30 minutes, "
                            f"or 'update' to tell me what's changed."
                        ),
                    },
                    "phoneNumberId": None,
                    "customer": {"number": phone},
                    "serverUrl": settings.vapi_webhook_url or f"{settings.webhook_base_url}/webhook/vapi",
                    "serverUrlSecret": settings.vapi_webhook_secret or settings.app_secret_key,
                    "metadata": {"task_id": task_id},
                },
            )

            if response.status_code == 201:
                data = response.json()
                logger.info("vapi_call_started", call_id=data.get("id"), to=phone)
                return {"status": "started", "call_id": data.get("id", "")}
            else:
                logger.error(
                    "vapi_call_failed",
                    status=response.status_code,
                    body=response.text[:200],
                )
                return {"status": "error", "error": response.text[:200]}

    except Exception as exc:
        logger.error("vapi_call_exception", error=str(exc))
        return {"status": "error", "error": str(exc)}
