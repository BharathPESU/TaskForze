"""Google OAuth2 authentication for Calendar, Gmail, and Tasks APIs.

Supports two modes:
1. Web-based OAuth flow (user clicks "Sign in with Google" in the frontend)
2. CLI-based flow (fallback via setup_auth.py)

The web flow uses a proper OAuth 2.0 Web Client ID created in GCP Console.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import structlog
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = structlog.get_logger(__name__)

# Scopes required by NEXUS agents
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
    "https://www.googleapis.com/auth/drive.file",
]

# File paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TOKEN_PATH = _PROJECT_ROOT / "token.json"
CREDENTIALS_PATH = _PROJECT_ROOT / "credentials.json"

# OAuth endpoints
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _load_client_config() -> dict:
    """Load OAuth client configuration from credentials.json or env vars."""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Priority 1: Environment variables
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

    if client_id and client_secret:
        return {"client_id": client_id, "client_secret": client_secret}

    # Priority 2: credentials.json
    if CREDENTIALS_PATH.exists():
        try:
            data = json.loads(CREDENTIALS_PATH.read_text())
            # Support both "web" and "installed" types
            config = data.get("web") or data.get("installed") or {}
            return {
                "client_id": config.get("client_id", ""),
                "client_secret": config.get("client_secret", ""),
            }
        except Exception as exc:
            logger.warning("credentials_load_failed", error=str(exc))

    return {"client_id": "", "client_secret": ""}


def get_oauth_client_id() -> str:
    """Get the OAuth Client ID."""
    return _load_client_config().get("client_id", "")


def has_oauth_client() -> bool:
    """Check if OAuth client credentials are configured."""
    config = _load_client_config()
    cid = config.get("client_id", "")
    # Reject the default/generic Google client that gets blocked
    if not cid or cid.startswith("764086051850"):
        return False
    return bool(config.get("client_secret"))


def get_auth_url(redirect_uri: str, state: str = "") -> str:
    """Generate Google OAuth2 authorization URL."""
    config = _load_client_config()
    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    if state:
        params["state"] = state

    return f"{GOOGLE_AUTH_URI}?{urlencode(params)}"


def exchange_code_for_tokens(code: str, redirect_uri: str) -> Optional[Credentials]:
    """Exchange an authorization code for access + refresh tokens."""
    import requests as req

    config = _load_client_config()
    payload = {
        "code": code,
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    resp = req.post(GOOGLE_TOKEN_URI, data=payload)
    if resp.status_code != 200:
        logger.error("token_exchange_failed", status=resp.status_code, body=resp.text[:500])
        return None

    token_data = resp.json()

    # Build Credentials object
    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=GOOGLE_TOKEN_URI,
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        scopes=SCOPES,
    )

    # Save token for future use
    TOKEN_PATH.write_text(creds.to_json())
    logger.info("oauth_token_saved", path=str(TOKEN_PATH))
    return creds


def get_google_credentials() -> Optional[Credentials]:
    """Get valid Google OAuth2 credentials.

    Returns None if no token exists.
    """
    creds: Optional[Credentials] = None

    # Load existing token
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception as exc:
            logger.warning("token_load_failed", error=str(exc))

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            logger.info("token_refreshed")
        except Exception as exc:
            logger.warning("token_refresh_failed", error=str(exc))
            creds = None

    if creds and creds.valid:
        return creds

    return None


def is_authenticated() -> bool:
    """Check if we have valid cached credentials."""
    return get_google_credentials() is not None


def logout() -> bool:
    """Remove cached credentials (sign out)."""
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
        logger.info("oauth_token_removed")
        return True
    return False


def save_credentials_file(client_id: str, client_secret: str) -> None:
    """Save OAuth client credentials to credentials.json (web type)."""
    creds_data = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [
                "http://localhost:8000/auth/callback",
                "http://localhost:3000",
            ],
        }
    }
    CREDENTIALS_PATH.write_text(json.dumps(creds_data, indent=2))
    logger.info("credentials_saved", path=str(CREDENTIALS_PATH))
