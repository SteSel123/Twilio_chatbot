"""Proactive outbound messaging — reminders, payments, reviews, follow-ups."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone

from config import BASE_DIR
from platform.analytics import record_message
from platform.payments import create_payment_link
from twilio_client import send_whatsapp

logger = logging.getLogger(__name__)

OUTBOUND_DB = BASE_DIR / ".user_data" / "outbound.db"

JOB_TYPES = ("reminder", "payment_link", "review_request", "reschedule", "follow_up", "custom")


def _connect() -> sqlite3.Connection:
    OUTBOUND_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(OUTBOUND_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS outbound_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                body TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                scheduled_at REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                sent_at REAL,
                error TEXT DEFAULT '',
                created_at REAL NOT NULL
            )
            """
        )


def schedule_message(
    tenant_id: str,
    user_id: str,
    job_type: str,
    body: str,
    scheduled_at: float | None = None,
    metadata: dict | None = None,
) -> int:
    _init_db()
    when = scheduled_at if scheduled_at is not None else time.time()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO outbound_jobs
            (tenant_id, user_id, job_type, body, metadata_json, scheduled_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tenant_id, user_id, job_type, body, json.dumps(metadata or {}), when, time.time()),
        )
        return int(cur.lastrowid)


def schedule_appointment_reminder(
    tenant_id: str,
    user_id: str,
    appointment_time: str,
    hours_before: float = 24,
    business_name: str = "",
) -> int:
    try:
        appt = datetime.fromisoformat(appointment_time)
        if appt.tzinfo is None:
            appt = appt.replace(tzinfo=timezone.utc)
    except ValueError:
        appt = datetime.now(timezone.utc)

    remind_at = appt.timestamp() - hours_before * 3600
    body = (
        f"Reminder: your appointment at {business_name or 'us'} is tomorrow at "
        f"{appt.strftime('%H:%M on %d %b')}. Reply RESCHEDULE if you need to change."
    )
    return schedule_message(
        tenant_id,
        user_id,
        "reminder",
        body,
        scheduled_at=remind_at,
        metadata={"appointment_time": appointment_time},
    )


def schedule_review_request(
    tenant_id: str,
    user_id: str,
    review_url: str,
    delay_hours: float = 2,
) -> int:
    body = f"Thanks for visiting us! We'd love your feedback: {review_url}"
    return schedule_message(
        tenant_id,
        user_id,
        "review_request",
        body,
        scheduled_at=time.time() + delay_hours * 3600,
        metadata={"review_url": review_url},
    )


def list_jobs(tenant_id: str, status: str | None = None, limit: int = 50) -> list[dict]:
    _init_db()
    query = "SELECT * FROM outbound_jobs WHERE tenant_id = ?"
    params: list = [tenant_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY scheduled_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def _send_job(row: sqlite3.Row) -> None:
    tenant_id = row["tenant_id"]
    user_id = row["user_id"]
    body = row["body"]
    meta = json.loads(row["metadata_json"] or "{}")

    if row["job_type"] == "payment_link":
        amount = int(meta.get("amount_cents", 0))
        if amount > 0:
            url = create_payment_link(
                amount_cents=amount,
                currency=meta.get("currency", "eur"),
                description=meta.get("description", "Payment"),
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if url:
                body = f"{body}\n\nPay here: {url}"

    from config import TWILIO_WHATSAPP_FROM
    from platform.business_profile import whatsapp_from_for_tenant

    send_whatsapp(
        user_id,
        body,
        from_=whatsapp_from_for_tenant(tenant_id, TWILIO_WHATSAPP_FROM) or None,
    )
    record_message(tenant_id, user_id, "outbound", message_preview=body[:200])

    with _connect() as conn:
        conn.execute(
            "UPDATE outbound_jobs SET status = 'sent', sent_at = ? WHERE id = ?",
            (time.time(), row["id"]),
        )


def process_due_messages(limit: int = 20) -> int:
    """Send pending outbound jobs whose scheduled_at has passed."""
    _init_db()
    now = time.time()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM outbound_jobs
            WHERE status = 'pending' AND scheduled_at <= ?
            ORDER BY scheduled_at ASC LIMIT ?
            """,
            (now, limit),
        ).fetchall()

    sent = 0
    for row in rows:
        try:
            _send_job(row)
            sent += 1
        except Exception as exc:
            logger.error("Outbound job %s failed: %s", row["id"], exc)
            with _connect() as conn:
                conn.execute(
                    "UPDATE outbound_jobs SET status = 'failed', error = ? WHERE id = ?",
                    (str(exc)[:500], row["id"]),
                )
    return sent
