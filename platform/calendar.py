"""Appointment booking — Google Calendar API or fallback link generation."""

from __future__ import annotations

import json
import logging
import sqlite3
import time as time_module
import urllib.parse
from datetime import datetime, timedelta, timezone

from config import BASE_DIR, GOOGLE_CALENDAR_CREDENTIALS_JSON
from platform.business_profile import load_business_profile

logger = logging.getLogger(__name__)

APPOINTMENTS_DB = BASE_DIR / ".user_data" / "appointments.db"


def _connect() -> sqlite3.Connection:
    APPOINTMENTS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(APPOINTMENTS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                service TEXT DEFAULT '',
                customer_name TEXT DEFAULT '',
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                status TEXT DEFAULT 'confirmed',
                calendar_event_id TEXT DEFAULT '',
                created_at REAL NOT NULL
            )
            """
        )


def _parse_slot(date_str: str, time_str: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(f"{date_str} {time_str}".strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def google_calendar_link(title: str, start: datetime, end: datetime, details: str = "") -> str:
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start.strftime('%Y%m%dT%H%M%SZ')}/{end.strftime('%Y%m%dT%H%M%SZ')}",
        "details": details,
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)


def list_available_slots(tenant_id: str, date_str: str) -> list[str]:
    """Return hourly slots 9–17, excluding local DB bookings and Google Calendar busy times."""
    _init_db()
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return []

    booked: set[str] = set()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT starts_at FROM appointments WHERE tenant_id = ? AND starts_at LIKE ? AND status != 'cancelled'",
            (tenant_id, f"{day.isoformat()}%"),
        ).fetchall()
        for row in rows:
            booked.add(row["starts_at"][11:16])

    google_busy: set[str] = set()
    try:
        from platform.google_oauth import busy_times_on_date

        google_busy = busy_times_on_date(tenant_id, day)
    except Exception:
        pass

    slots = []
    for hour in range(9, 17):
        slot = f"{hour:02d}:00"
        if slot not in booked and slot not in google_busy:
            slots.append(slot)
    return slots


def book_appointment(
    tenant_id: str,
    user_id: str,
    *,
    date: str,
    slot_time: str,
    service: str = "",
    customer_name: str = "",
    customer_email: str = "",
    owner_email: str = "",
    duration_minutes: int = 60,
) -> dict:
    """Book an appointment; sync to Google Calendar when credentials are configured."""
    _init_db()
    profile = load_business_profile(tenant_id)
    start = _parse_slot(date, slot_time)
    if not start:
        return {"ok": False, "error": "Invalid date/time format. Use YYYY-MM-DD and HH:MM."}

    end = start + timedelta(minutes=duration_minutes)
    title = f"{profile.business_name} — {service or 'Appointment'}"
    details = f"Customer: {customer_name or user_id}"
    if customer_email:
        details += f" ({customer_email})"
    details += f"\nService: {service}"

    invite_emails = [
        e.strip().lower()
        for e in (customer_email, owner_email)
        if e and "@" in e and not e.strip().lower().endswith("@pending.local")
    ]
    invite_emails = list(dict.fromkeys(invite_emails))

    event_id = ""
    from platform.google_oauth import create_calendar_event

    event_id = create_calendar_event(
        tenant_id, title, start, end, details, attendee_emails=invite_emails
    )
    if not event_id and GOOGLE_CALENDAR_CREDENTIALS_JSON:
        event_id = _create_google_event(profile, title, start, end, details)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO appointments
            (tenant_id, user_id, service, customer_name, starts_at, ends_at, calendar_event_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                user_id,
                service,
                customer_name,
                start.isoformat(),
                end.isoformat(),
                event_id,
                time_module.time(),
            ),
        )

    cal_link = google_calendar_link(title, start, end, details)
    return {
        "ok": True,
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
        "service": service,
        "calendar_link": cal_link,
        "google_synced": bool(event_id),
        "oauth_calendar": bool(event_id),
        "invites_sent": invite_emails,
    }


def _create_google_event(profile, title: str, start: datetime, end: datetime, details: str) -> str:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_info = json.loads(GOOGLE_CALENDAR_CREDENTIALS_JSON)
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        service = build("calendar", "v3", credentials=creds)
        calendar_id = getattr(profile, "google_calendar_id", None) or "primary"
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
        logger.warning("Google Calendar sync failed: %s", exc)
        return ""
