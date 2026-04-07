#!/usr/bin/env python3
"""NEXUS — Google OAuth2 Setup Script

Run this ONCE to connect your Google Calendar, Gmail, and Tasks.
It will open a browser for you to sign in with your Google account.

Usage:
    python setup_auth.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from nexus.tools.google_auth import authenticate_interactive, is_authenticated, TOKEN_PATH


def main():
    print("\n" + "=" * 60)
    print("  🔗 NEXUS — Google Account Setup")
    print("=" * 60)
    print()

    if is_authenticated():
        print("✅ Already authenticated! Token found at:")
        print(f"   {TOKEN_PATH}")
        print()
        reauth = input("Re-authenticate? (y/N): ").strip().lower()
        if reauth != "y":
            print("Using existing credentials.")
            return

    print("This will connect NEXUS to your Google account.")
    print("Permissions requested:")
    print("  📅 Google Calendar — read & write events")
    print("  📧 Gmail — read inbox, send emails")
    print("  ✅ Google Tasks — read & write tasks")
    print()
    print("A browser window will open for you to sign in...")
    print()

    try:
        creds = authenticate_interactive()
        print()
        print("=" * 60)
        print("  ✅ SUCCESS — Google account connected!")
        print("=" * 60)
        print()
        print(f"Token saved to: {TOKEN_PATH}")
        print()
        print("NEXUS can now:")
        print("  • Read your real calendar events")
        print("  • Scan your Gmail inbox for action items")
        print("  • Create and manage tasks in Google Tasks")
        print("  • Send emails on your behalf")
        print()
        print("Restart the server to use live integrations:")
        print("  .venv/bin/uvicorn nexus.main:app --reload --port 8000")
        print()

    except Exception as exc:
        print(f"\n❌ Authentication failed: {exc}")
        print("\nTroubleshooting:")
        print("  1. Make sure you have a browser installed")
        print("  2. Check that port 8090 is free")
        print("  3. Try again, or create OAuth credentials in GCP Console")
        sys.exit(1)


if __name__ == "__main__":
    main()
