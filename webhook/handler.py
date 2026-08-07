"""Inbound webhook processing."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from platform.events import publish
from platform.i18n import t
from platform.observability import correlation_id_var, log_structured, new_correlation_id
from platform.queue import enqueue_message_processing
from schemas.normalized_message import NormalizedMessage, from_twilio_form
from security import encode_outbound_text, is_allowed_media_url, sanitize_text
from twilio_client import send_whatsapp
from webhook.idempotency import is_duplicate

logger = logging.getLogger(__name__)

RESET_COMMANDS = {"reset", "clear", "start over", "new conversation"}


def process_status_callback(form: dict[str, str]) -> None:
    message_sid = form.get("MessageSid", "")
    message_status = form.get("MessageStatus", "")
    to = form.get("To", "")
    error_code = form.get("ErrorCode", "")
    error_message = form.get("ErrorMessage", "")

    if message_status == "failed" or error_code or error_message:
        logger.warning(
            "Delivery status: sid=%s status=%s to=%s error_code=%s error_message=%s",
            message_sid,
            message_status,
            to,
            error_code,
            error_message,
        )
    else:
        logger.info(
            "Delivery status: sid=%s status=%s to=%s",
            message_sid,
            message_status,
            to,
        )


def _sanitize_message(msg: NormalizedMessage) -> NormalizedMessage:
    safe_media = [
        item for item in msg["media"] if is_allowed_media_url(item.get("url", ""))
    ]
    if len(safe_media) < len(msg["media"]):
        logger.warning("Blocked %d non-Twilio media URL(s)", len(msg["media"]) - len(safe_media))

    return NormalizedMessage(
        channel=msg["channel"],
        user_id=msg["user_id"],
        text=sanitize_text(msg["text"]),
        media=safe_media,
        message_sid=msg["message_sid"],
        timestamp=msg["timestamp"],
        provider=msg["provider"],
    )


def _process_and_reply(
    msg: NormalizedMessage,
    agent_handle: Callable[..., str],
    tenant_id: str,
    whatsapp_from: str = "",
) -> None:
    correlation_id = new_correlation_id()
    correlation_id_var.set(correlation_id)
    user_id = msg["user_id"]
    body = msg["text"]
    media_items = msg["media"]

    logger.info("[%s] Processing message from %s", correlation_id, user_id)

    if body and body.lower() not in RESET_COMMANDS:
        try:
            from platform.i18n import detect_language

            lang = detect_language(body)
            send_whatsapp(user_id, t("ack", lang), from_=whatsapp_from or None)
        except Exception:
            logger.warning("[%s] Failed to send ack to %s", correlation_id, user_id)

    try:
        reply_text = agent_handle(
            user_id,
            body,
            media_items=media_items,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
        )
    except Exception:
        logger.exception("[%s] Agent error", correlation_id)
        reply_text = (
            "Something went wrong while processing your message. "
            "Please try again or rephrase your question."
        )

    try:
        send_whatsapp(user_id, encode_outbound_text(reply_text), from_=whatsapp_from or None)
        publish("message.sent", {"correlation_id": correlation_id, "user_id": user_id})
        log_structured("reply_sent", user_id=user_id)
        logger.info("[%s] Reply sent to %s", correlation_id, user_id)
    except Exception:
        logger.exception("[%s] Failed to send WhatsApp reply to %s", correlation_id, user_id)


def process_inbound_async(
    form: dict[str, str],
    agent_handle: Callable[..., str],
    tenant_id: str = "default",
    whatsapp_from: str = "",
) -> bool:
    """
    Normalize, dedupe, and process an inbound message via Redis queue or background thread.
    Returns False if duplicate MessageSid (caller should still return 200 TwiML).
    """
    msg = _sanitize_message(from_twilio_form(form))

    if is_duplicate(msg["message_sid"]):
        logger.info("Duplicate MessageSid ignored: %s", msg["message_sid"])
        return False

    logger.info(
        "Message from %s: %s (media=%d, sid=%s)",
        msg["user_id"],
        msg["text"][:80] if msg["text"] else "[no text]",
        len(msg["media"]),
        msg["message_sid"],
    )

    def _inline():
        _process_and_reply(msg, agent_handle, tenant_id, whatsapp_from=whatsapp_from)

    enqueued = enqueue_message_processing(form, tenant_id, inline_fn=_inline)
    if not enqueued:
        threading.Thread(target=_inline, daemon=True).start()
    return True
