"""Google Calendar OAuth — per-tenant, no service account required."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

from config import (
    BASE_DIR,
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
    WEBHOOK_BASE_URL,
)
from platform.business_profile import load_business_profile

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]
OAUTH_DB = BASE_DIR / ".user_data" / "google_oauth.db"


def oauth_configured() -> bool:
    return bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET)


def _redirect_uri() -> str:
    return GOOGLE_OAUTH_REDIRECT_URI or f"{(WEBHOOK_BASE_URL or 'http://localhost:5000').rstrip('/')}/onboard/google/callback"


def _connect() -> sqlite3.Connection:
    OAUTH_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(OAUTH_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS google_tokens (
                tenant_id TEXT PRIMARY KEY,
                refresh_token TEXT NOT NULL,
                access_token TEXT DEFAULT '',
                expires_at REAL DEFAULT 0,
                calendar_id TEXT DEFAULT 'primary',
                connected_email TEXT DEFAULT '',
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                setup_token TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )


def is_connected(tenant_id: str) -> bool:
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT refresh_token FROM google_tokens WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    return bool(row and row["refresh_token"])


def get_connection_info(tenant_id: str) -> dict:
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT calendar_id, connected_email, updated_at FROM google_tokens WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    if not row:
        return {"connected": False}
    return {
        "connected": True,
        "calendar_id": row["calendar_id"],
        "email": row["connected_email"],
        "updated_at": row["updated_at"],
    }


def create_authorization_url(tenant_id: str, setup_token: str) -> str:
    if not oauth_configured():
        raise RuntimeError("Google OAuth not configured")

    import secrets

    _init_db()
    state = secrets.token_urlsafe(24)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO oauth_states (state, tenant_id, setup_token, expires_at) VALUES (?, ?, ?, ?)",
            (state, tenant_id, setup_token, time.time() + 600),
        )

    params = {
        "client_id": GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def _pop_oauth_state(state: str) -> dict | None:
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT tenant_id, setup_token, expires_at FROM oauth_states WHERE state = ?",
            (state,),
        ).fetchone()
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    if not row or time.time() > row["expires_at"]:
        return None
    return {"tenant_id": row["tenant_id"], "setup_token": row["setup_token"]}


def handle_oauth_callback(code: str, state: str) -> dict:
    """Exchange code for tokens and store per tenant."""
    meta = _pop_oauth_state(state)
    if not meta:
        raise ValueError("Invalid or expired OAuth state")

    import requests

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": _redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    refresh = data.get("refresh_token", "")
    access = data.get("access_token", "")
    expires_in = int(data.get("expires_in", 3600))

    if not refresh:
        raise ValueError("No refresh token — revoke app access in Google Account and retry")

    tenant_id = meta["tenant_id"]
    profile = load_business_profile(tenant_id)
    calendar_id = profile.google_calendar_id or "primary"

    _init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO google_tokens
            (tenant_id, refresh_token, access_token, expires_at, calendar_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id) DO UPDATE SET
                refresh_token = excluded.refresh_token,
                access_token = excluded.access_token,
                expires_at = excluded.expires_at,
                calendar_id = excluded.calendar_id,
                updated_at = excluded.updated_at
            """,
            (
                tenant_id,
                refresh,
                access,
                time.time() + expires_in - 60,
                calendar_id,
                time.time(),
            ),
        )

    return {"tenant_id": tenant_id, "setup_token": meta["setup_token"]}


def _get_credentials(tenant_id: str):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT refresh_token, access_token, expires_at FROM google_tokens WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    if not row:
        return None

    creds = Credentials(
        token=row["access_token"] or None,
        refresh_token=row["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_OAUTH_CLIENT_ID,
        client_secret=GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with _connect() as conn:
            conn.execute(
                """
                UPDATE google_tokens SET access_token = ?, expires_at = ?, updated_at = ?
                WHERE tenant_id = ?
                """,
                (creds.token, time.time() + 3500, time.time(), tenant_id),
            )
    return creds


def create_calendar_event(
    tenant_id: str,
    title: str,
    start: datetime,
    end: datetime,
    details: str = "",
) -> str:
    """Create event via OAuth credentials; returns event id or empty string."""
    if not is_connected(tenant_id):
        return ""

    try:
        from googleapiclient.discovery import build

        creds = _get_credentials(tenant_id)
        if not creds:
            return ""

        profile = load_business_profile(tenant_id)
        calendar_id = profile.google_calendar_id or "primary"
        service = build("calendar", "v3", credentials=creds)
        event = service.events().insert(
            calendarId=calendar_id,
            body={
                "summary": title,
                "description": details,
                "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
            },
        ).execute()
        return event.get("id", "")
    except Exception as exc:
        logger.warning("OAuth calendar event failed for %s: %s", tenant_id, exc)
        return ""


def busy_times_on_date(tenant_id: str, day) -> set[str]:
    """Return HH:MM slots blocked on Google Calendar for a date (OAuth tenants)."""
    if not is_connected(tenant_id):
        return set()

    try:
        from datetime import date, datetime, time, timezone

        from googleapiclient.discovery import build

        if isinstance(day, str):
            day = date.fromisoformat(day)

        creds = _get_credentials(tenant_id)
        if not creds:
            return set()

        profile = load_business_profile(tenant_id)
        calendar_id = profile.google_calendar_id or "primary"
        start = datetime.combine(day, time(9, 0), tzinfo=timezone.utc)
        end = datetime.combine(day, time(17, 0), tzinfo=timezone.utc)
        service = build("calendar", "v3", credentials=creds)
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "items": [{"id": calendar_id}],
        }
        result = service.freebusy().query(body=body).execute()
        busy = result.get("calendars", {}).get(calendar_id, {}).get("busy", [])
        blocked: set[str] = set()
        for slot in busy:
            start_dt = datetime.fromisoformat(slot["start"].replace("Z", "+00:00"))
            blocked.add(start_dt.strftime("%H:%M"))
        return blocked
    except Exception as exc:
        logger.warning("Google Calendar freebusy failed for %s: %s", tenant_id, exc)
        return set()
