"""NEXUS FastAPI Application — Multi-Agent Workflow Intelligence Layer.

Endpoints:
    POST /chat              → SSE stream of agent reasoning + final response
    POST /chat/sync         → Non-streaming chat
    GET  /workflows         → List past workflow runs
    GET  /workflows/{id}    → Replay a specific workflow
    GET  /agents/status     → Live status of all 5 agents
    GET  /webhook/whatsapp  → Meta WhatsApp webhook verification
    POST /webhook/whatsapp  → Handle WhatsApp button replies / inbound text
    POST /webhook/twilio    → Legacy Twilio compatibility
    POST /webhook/vapi      → Handle voice call outcomes
    GET  /tasks             → Task list with priority scores
    POST /tasks             → Create task directly
    GET  /health            → Health check
    GET  /auth/status       → Google OAuth connection status
    GET  /auth/login        → Start Google OAuth flow
    GET  /auth/callback     → OAuth callback handler
    POST /auth/setup        → Save OAuth client credentials
    POST /auth/logout       → Sign out
"""

from __future__ import annotations

import os
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nexus.config import settings
from nexus.routers import chat, webhooks, workflows
from nexus.scheduler.reminder_scheduler import start_scheduler, stop_scheduler

# ── Structured Logging ────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
logger = structlog.get_logger(__name__)

try:
    import logfire
except Exception:
    logfire = None

if logfire:
    logfire.configure(token=settings.logfire_token or None)


# ── Lifespan (startup/shutdown) ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — start scheduler, create tables."""
    logger.info("nexus_starting", version="2.0.0")

    # Create DB tables (if using SQLite fallback or fresh DB)
    try:
        from nexus.db.engine import engine
        from nexus.db.models import Base
        from nexus.db.schema import ensure_sqlite_schema_compat

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            await ensure_sqlite_schema_compat(engine)
        logger.info("database_tables_ready")
    except Exception as exc:
        logger.warning("database_setup_skipped", error=str(exc))

    # Start the reminder scheduler
    start_scheduler()

    yield

    # Shutdown
    stop_scheduler()
    logger.info("nexus_shutdown")


# ── FastAPI App ───────────────────────────────────────────────────────
app = FastAPI(
    title="NEXUS",
    description="Multi-Agent Workflow Intelligence Layer — The AI assistant that won't let you forget.",
    version="2.0.0",
    lifespan=lifespan,
)

if logfire:
    logfire.instrument_fastapi(app)

# ── CORS ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        settings.frontend_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────
app.include_router(chat.router)
app.include_router(webhooks.router)
app.include_router(workflows.router)

# ── Static files (React build) ────────────────────────────────────────
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dist, "index.html"))


# ═══════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/auth/status")
async def auth_status():
    """Check Google OAuth connection status."""
    from nexus.tools.google_auth import is_authenticated, has_oauth_client

    authenticated = is_authenticated()
    result = {
        "authenticated": authenticated,
        "has_oauth_client": has_oauth_client(),
        "services": {
            "google_calendar": authenticated,
            "gmail": authenticated,
            "google_tasks": authenticated,
        },
    }
    if authenticated:
        try:
            from nexus.tools.gmail_tools import get_profile
            profile = await get_profile()
            result["email"] = profile.get("email", "unknown")
        except Exception:
            result["email"] = "connected"
    return result


@app.get("/auth/login")
async def auth_login(request: Request):
    """Start the Google OAuth2 login flow — redirects to Google."""
    from nexus.tools.google_auth import has_oauth_client, get_auth_url, is_authenticated

    frontend_base = settings.frontend_url.rstrip("/")

    if is_authenticated():
        return RedirectResponse(url=f"{frontend_base}/?auth=already_connected")

    if not has_oauth_client():
        return RedirectResponse(url=f"{frontend_base}/?auth=needs_setup")

    # Determine the callback URL using literal settings instead of dynamic base_url to prevent localhost vs 127.0.0.1 mismatch
    callback_url = settings.webhook_base_url.rstrip("/") + "/auth/callback"
    auth_url = get_auth_url(redirect_uri=callback_url)

    logger.info("oauth_login_redirect", callback=callback_url)
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", error: str = ""):
    """Handle the OAuth2 callback from Google."""
    from nexus.tools.google_auth import exchange_code_for_tokens

    frontend_base = settings.frontend_url.rstrip("/")

    if error:
        logger.error("oauth_callback_error", error=error)
        return RedirectResponse(url=f"{frontend_base}/?auth=error&message={error}")

    if not code:
        return RedirectResponse(url=f"{frontend_base}/?auth=error&message=no_code")

    # Exchange the authorization code for tokens
    callback_url = settings.webhook_base_url.rstrip("/") + "/auth/callback"
    creds = exchange_code_for_tokens(code, redirect_uri=callback_url)

    if creds:
        logger.info("oauth_login_success")
        return RedirectResponse(url=f"{frontend_base}/?auth=success")
    else:
        logger.error("oauth_token_exchange_failed")
        return RedirectResponse(url=f"{frontend_base}/?auth=error&message=token_exchange_failed")


class OAuthSetupRequest(BaseModel):
    client_id: str
    client_secret: str


@app.post("/auth/setup")
async def auth_setup(body: OAuthSetupRequest):
    """Save OAuth client credentials (one-time setup)."""
    from nexus.tools.google_auth import save_credentials_file

    if not body.client_id or not body.client_secret:
        return {"status": "error", "message": "client_id and client_secret are required"}

    save_credentials_file(body.client_id, body.client_secret)
    logger.info("oauth_client_configured")
    return {
        "status": "success",
        "message": "OAuth credentials saved. You can now sign in with Google.",
    }


@app.post("/auth/logout")
async def auth_logout():
    """Sign out — remove cached tokens."""
    from nexus.tools.google_auth import logout

    removed = logout()
    return {
        "status": "success" if removed else "no_session",
        "message": "Signed out successfully." if removed else "No active session.",
    }


# ═══════════════════════════════════════════════════════════════════════
# DATA SYNC ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/drive/sync")
async def api_drive_sync():
    """Manually trigger a sync of all NEXUS data to Google Drive."""
    from nexus.db.engine import get_db_context
    from nexus.tools.drive_tools import sync_data_to_drive
    
    try:
        async with get_db_context() as session:
            result = await sync_data_to_drive(session)
        return result
    except Exception as e:
        logger.error("api_drive_sync_failed", exc_info=e)
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run / monitoring."""
    from nexus.tools.google_auth import is_authenticated, has_oauth_client

    authenticated = is_authenticated()
    return {
        "status": "ok",
        "service": "nexus",
        "version": "2.0.0",
        "agents": 5,
        "oauth_configured": has_oauth_client(),
        "integrations": {
            "google_calendar": "connected" if authenticated else "not_connected",
            "gmail": "connected" if authenticated else "not_connected",
            "google_tasks": "connected" if authenticated else "not_connected",
            "gemini_ai": "connected" if settings.google_api_key else "demo_mode",
        },
    }
