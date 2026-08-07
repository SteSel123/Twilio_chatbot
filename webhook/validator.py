"""Twilio webhook signature validation (WC-16)."""

from __future__ import annotations

import logging

from flask import Request
from twilio.request_validator import RequestValidator

from config import ENFORCE_TWILIO_HMAC, TWILIO_AUTH_TOKEN, WEBHOOK_BASE_URL

logger = logging.getLogger(__name__)

_validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None


def validate_twilio_request(req: Request) -> bool:
    if not _validator or not WEBHOOK_BASE_URL:
        if ENFORCE_TWILIO_HMAC:
            logger.error("HMAC enforced but TWILIO_AUTH_TOKEN or WEBHOOK_BASE_URL missing")
            return False
        return True
    signature = req.headers.get("X-Twilio-Signature", "")
    url = WEBHOOK_BASE_URL.rstrip("/") + req.path
    valid = _validator.validate(url, req.form.to_dict(), signature)
    if not valid:
        logger.warning("Invalid Twilio signature for %s", req.path)
    return valid
