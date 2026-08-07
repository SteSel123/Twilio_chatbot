"""Twilio REST client for outbound WhatsApp messages (API key auth)."""

from __future__ import annotations

import logging
import time

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_API_KEY,
    TWILIO_API_SECRET,
    TWILIO_WHATSAPP_FROM,
    WEBHOOK_BASE_URL,
)

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(TWILIO_API_KEY, TWILIO_API_SECRET, TWILIO_ACCOUNT_SID)
    return _client


def _status_callback_url() -> str | None:
    if not WEBHOOK_BASE_URL:
        return None
    return f"{WEBHOOK_BASE_URL.rstrip('/')}/webhook/status"


def send_whatsapp(to: str, body: str, max_retries: int = 3, from_: str | None = None) -> str:
    """Send a WhatsApp message via Twilio Messages API with retry on transient errors."""
    kwargs: dict[str, str] = {
        "from_": from_ or TWILIO_WHATSAPP_FROM,
        "to": to,
        "body": body,
    }
    status_callback = _status_callback_url()
    if status_callback:
        kwargs["status_callback"] = status_callback

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            message = get_client().messages.create(**kwargs)
            logger.info("WhatsApp reply sent to %s (sid=%s)", to, message.sid)
            return message.sid
        except TwilioRestException as exc:
            last_exc = exc
            retryable = exc.status in (429, 500, 502, 503, 504) if exc.status else False
            if not retryable or attempt == max_retries - 1:
                raise
            delay = 2**attempt
            logger.warning(
                "Twilio send failed (attempt %d/%d, status=%s), retry in %ds",
                attempt + 1,
                max_retries,
                exc.status,
                delay,
            )
            time.sleep(delay)

    if last_exc:
        raise last_exc
    raise RuntimeError("send_whatsapp failed without exception")
