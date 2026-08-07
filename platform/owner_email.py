"""E-mail notifications to business owners (conversation summaries, appointments)."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import (
    BASE_DIR,
    NOTIFY_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)

logger = logging.getLogger(__name__)

OUTBOX_DIR = BASE_DIR / ".user_data" / "email_outbox"


def smtp_configured() -> bool:
    return bool(SMTP_HOST and NOTIFY_FROM_EMAIL)


def _format_email_body(
    *,
    business_name: str,
    question: str,
    answer: str,
    summary: str,
    appointment: str = "",
) -> str:
    lines = [
        f"Hoi {business_name},",
        "",
        "Er is zojuist een klantgesprek via WhatsApp (AppAssist):",
        "",
        "── Klant ──",
        question,
        "",
        "── AppAssist antwoord ──",
        answer,
        "",
        "── Samenvatting ──",
        summary,
    ]
    if appointment:
        lines.extend(["", "── Afspraak ──", appointment])
    lines.extend([
        "",
        "— AppAssist",
        "Dit is een automatische samenvatting. Antwoord klanten via WhatsApp of je dashboard.",
    ])
    return "\n".join(lines)


def send_owner_summary(
    *,
    to_email: str,
    business_name: str,
    question: str,
    answer: str,
    summary: str,
    appointment: str = "",
) -> dict:
    """Send conversation summary to business owner. Queues to outbox if SMTP unavailable."""
    if not to_email:
        return {
            "email_sent": False,
            "email_to": "",
            "email_subject": "",
            "email_body": "",
            "email_note": "Geen e-mailadres bekend voor dit account.",
        }

    subject = f"AppAssist — klantgesprek · {business_name}"
    body = _format_email_body(
        business_name=business_name,
        question=question,
        answer=answer,
        summary=summary,
        appointment=appointment,
    )

    if smtp_configured():
        try:
            msg = MIMEMultipart()
            msg["From"] = NOTIFY_FROM_EMAIL
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                if SMTP_USE_TLS:
                    server.starttls()
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(NOTIFY_FROM_EMAIL, [to_email], msg.as_string())

            logger.info("Owner summary email sent to %s for %s", to_email, business_name)
            return {
                "email_sent": True,
                "email_to": to_email,
                "email_subject": subject,
                "email_body": body,
                "email_note": f"Samenvatting verstuurd naar {to_email}",
            }
        except Exception as exc:
            logger.error("SMTP send failed: %s", exc)
            queued = _queue_outbox(to_email, subject, body)
            return {
                "email_sent": False,
                "email_to": to_email,
                "email_subject": subject,
                "email_body": body,
                "email_note": f"Verzenden mislukt — opgeslagen in outbox ({queued.name})",
            }

    queued = _queue_outbox(to_email, subject, body)
    return {
        "email_sent": False,
        "email_to": to_email,
        "email_subject": subject,
        "email_body": body,
        "email_note": f"E-mail klaargezet (SMTP niet geconfigureerd) → {queued.name}",
    }


def _queue_outbox(to_email: str, subject: str, body: str) -> Path:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = to_email.replace("@", "_at_").replace(".", "_")
    path = OUTBOX_DIR / f"{stamp}-{safe}.txt"
    path.write_text(f"To: {to_email}\nSubject: {subject}\n\n{body}", encoding="utf-8")
    return path
