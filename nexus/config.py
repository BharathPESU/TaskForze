"""Centralized configuration — 12-factor compliant via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings sourced from env vars / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App identity ─────────────────────────────────────────
    app_name: str = "nexus"
    default_user_id: str = "user_01"

    # ── Google AI ─────────────────────────────────────────────
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    vertex_project_id: str = ""
    vertex_location: str = "asia-south1"

    # ── Database ──────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"

    # ── User contact ─────────────────────────────────────────
    user_whatsapp_number: str = ""

    # ── Meta WhatsApp Cloud API ──────────────────────────────
    whatsapp_phone_id: str = ""
    whatsapp_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""

    # ── Vapi ──────────────────────────────────────────────────
    vapi_api_key: str = ""
    vapi_webhook_url: str = ""
    vapi_webhook_secret: str = ""

    # ── Gmail / IMAP ─────────────────────────────────────────
    gmail_address: str = ""
    gmail_app_password: str = ""

    # ── MCP tool servers ─────────────────────────────────────
    gcal_mcp_url: str = ""
    gcal_mcp_token: str = ""
    gmail_mcp_url: str = ""
    gmail_mcp_token: str = ""

    # ── Frontend / observability ─────────────────────────────
    frontend_url: str = "http://localhost:5173"
    logfire_token: str = ""

    # ── App ───────────────────────────────────────────────────
    app_secret_key: str = "change-this-in-production"
    webhook_base_url: str = "http://localhost:8000"
    user_name: str = "User"

    # ── Scheduler ─────────────────────────────────────────────
    reminder_poll_seconds: int = 60
    reminder_t120_minutes: int = 120
    reminder_t30_minutes: int = 30
    escalation_wait_minutes: int = 10


settings = Settings()
