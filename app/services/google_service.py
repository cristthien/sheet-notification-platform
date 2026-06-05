"""
Google OAuth service.

Two separate OAuth flows:
  1. Login flow  — scopes: openid, email, profile
  2. Sheets flow — scopes: spreadsheets.readonly, drive.readonly

Token revoke handling:
  - Before every Sheets API call, check if access_token expires in < 5 minutes
  - If expired → attempt refresh using refresh_token
  - If refresh fails (RefreshError) → token was revoked by user
    → pause all watches, notify user via their active notification configs
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

# Allow Google to return broader scopes than requested (e.g. after Sheets connect)
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

import google.auth.exceptions
import google.auth.transport.requests
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.core.config import settings
from app.models.user import User


# ─── Custom exception ──────────────────────────────────────────────────────────

class TokenRevokedException(Exception):
    """Raised when Google refresh token is invalid/revoked."""
    pass


# ─── OAuth Flow Builders ───────────────────────────────────────────────────────

def _build_client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [
                settings.google_login_redirect_uri,
                settings.google_sheets_redirect_uri,
            ],
        }
    }


def get_login_flow() -> Flow:
    """OAuth flow for user authentication (login)."""
    flow = Flow.from_client_config(
        _build_client_config(),
        scopes=settings.GOOGLE_LOGIN_SCOPES,
    )
    flow.redirect_uri = settings.google_login_redirect_uri
    return flow


def get_sheets_flow() -> Flow:
    """OAuth flow for Google Sheets access (separate from login)."""
    flow = Flow.from_client_config(
        _build_client_config(),
        scopes=settings.GOOGLE_SHEETS_SCOPES,
    )
    flow.redirect_uri = settings.google_sheets_redirect_uri
    return flow


def get_login_authorization_url() -> tuple[str, str]:
    """Returns (auth_url, state) for the login OAuth flow."""
    flow = get_login_flow()
    url, state = flow.authorization_url(
        access_type="offline",
        prompt="select_account",
        # NOTE: do NOT set include_granted_scopes=true here — it causes
        # Google to return combined scopes (login + sheets) which triggers
        # an oauthlib scope mismatch error on the login callback.
    )
    return url, state


def get_sheets_authorization_url() -> tuple[str, str]:
    """Returns (auth_url, state) for the Sheets OAuth flow."""
    flow = get_sheets_flow()
    url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",    # Force consent to always get refresh_token
        include_granted_scopes="false",
    )
    return url, state


# ─── Token Exchange ────────────────────────────────────────────────────────────

def exchange_login_code(code: str) -> dict:
    """
    Exchange auth code for tokens (login flow).
    Returns user info dict: {google_id, email, name, avatar_url}.
    """
    import httpx

    flow = get_login_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials

    # Get user info from Google
    with httpx.Client() as client:
        resp = client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        resp.raise_for_status()
        info = resp.json()

    return {
        "google_id": info["sub"],
        "email": info["email"],
        "name": info.get("name", info["email"]),
        "avatar_url": info.get("picture"),
    }


def exchange_sheets_code(code: str) -> dict:
    """
    Exchange auth code for Sheets tokens.
    Returns token dict to be stored on User.
    """
    flow = get_sheets_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    return {
        "sheets_access_token": creds.token,
        "sheets_refresh_token": creds.refresh_token,
        "sheets_token_expiry": creds.expiry,   # datetime (UTC)
        "sheets_token_scope": " ".join(creds.scopes or []),
        "sheets_connected": True,
        "sheets_revoked": False,
    }


# ─── Token Lifecycle Management ───────────────────────────────────────────────

async def get_valid_credentials(user: User) -> Credentials:
    """
    Return valid Google Credentials for the given user.

    Refresh token automatically if expiry is within 5 minutes.
    Raise TokenRevokedException if refresh fails (user revoked access).
    """
    if not user.sheets_connected or not user.sheets_refresh_token:
        raise TokenRevokedException(f"User {user.email} has no Sheets credentials")

    creds = Credentials(
        token=user.sheets_access_token,
        refresh_token=user.sheets_refresh_token,
        expiry=user.sheets_token_expiry,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )

    # Refresh proactively if expiring within 5 minutes
    now_utc = datetime.now(timezone.utc)
    expiry = creds.expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    needs_refresh = (
        not creds.token
        or expiry is None
        or (expiry - now_utc) < timedelta(minutes=5)
    )

    if needs_refresh:
        try:
            request = google.auth.transport.requests.Request()
            creds.refresh(request)

            # Persist new token to DB
            new_expiry = creds.expiry
            await user.set({
                "sheets_access_token": creds.token,
                "sheets_token_expiry": new_expiry,
            })
            print(f"🔄 Token refreshed for {user.email}, new expiry: {new_expiry}")

        except google.auth.exceptions.RefreshError as e:
            print(f"❌ Token revoked for {user.email}: {e}")
            await _handle_revoke(user)
            raise TokenRevokedException(
                f"Google Sheets access revoked for {user.email}"
            )

    return creds


async def _handle_revoke(user: User) -> None:
    """
    Handle token revocation:
    - Mark user as revoked
    - Pause all their active watches
    - Send warning notification via any still-working notification configs
    """
    from app.models.sheet_watch import SheetWatch
    from app.models.notification_config import NotificationConfig

    # Mark user
    await user.set({
        "sheets_revoked": True,
        "sheets_connected": False,
        "sheets_access_token": None,
    })

    # Pause all watches
    watches = await SheetWatch.find(
        SheetWatch.user_id == user.id,
        SheetWatch.is_active == True
    ).to_list()

    for watch in watches:
        await watch.set({
            "is_active": False,
            "last_error": "Google token revoked — reconnect required",
        })

    # Attempt to warn user via Telegram (best-effort)
    await _send_revoke_warning(user, watches)


async def _send_revoke_warning(user: User, paused_watches: list) -> None:
    """Send a warning message to user's notification channels."""
    from app.models.notification_config import NotificationConfig
    from app.services.notification.factory import get_notifier

    watch_ids = [w.id for w in paused_watches]
    if not watch_ids:
        return

    configs = await NotificationConfig.find(
        {"watch_id": {"$in": watch_ids}, "is_active": True}
    ).to_list()

    message = (
        f"⚠️ <b>Sheet Notifier Alert</b>\n\n"
        f"Hi <b>{user.name}</b>, your Google Sheets connection has been revoked "
        f"or expired.\n\n"
        f"<b>{len(paused_watches)}</b> sheet watch(es) have been paused.\n\n"
        f"👉 Please reconnect at: <a href='{settings.app_base_url}/dashboard'>"
        f"{settings.app_base_url}/dashboard</a>"
    )

    for config in configs:
        try:
            notifier = get_notifier(config.channel_type)
            await notifier.send(message, config.config)
        except Exception as e:
            print(f"⚠️ Failed to send revoke warning via {config.channel_type}: {e}")


# ─── gspread client builder ────────────────────────────────────────────────────

async def get_gspread_client(user: User) -> gspread.Client:
    """Return an authenticated gspread client for the user."""
    creds = await get_valid_credentials(user)
    return gspread.authorize(creds)
