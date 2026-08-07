"""Human advisor handoff."""

from __future__ import annotations

import json
import logging

import requests

from config import HANDOFF_EMAIL, HANDOFF_WEBHOOK_URL, SLACK_WEBHOOK_URL
from platform.business_profile import load_business_profile
from platform.observability import log_structured

logger = logging.getLogger(__name__)

HANDOFF_TRIGGERS = (
    "speak to human", "talk to human", "human advisor", "real person",
    "spreek met iemand", "mensen", "adviseur", "help me human",
)


def wants_handoff(message: str) -> bool:
    lower = message.lower()
    return any(t in lower for t in HANDOFF_TRIGGERS)


def request_handoff(user_id: str, tenant_id: str, case_summary: str = "") -> bool:
    log_structured("handoff_requested", user_id=user_id, tenant_id=tenant_id)

    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "case_summary": case_summary[:2000],
        "channel": "whatsapp",
    }

    profile = load_business_profile(tenant_id)
    slack_url = profile.handoff_slack_webhook or SLACK_WEBHOOK_URL

    if slack_url:
        try:
            resp = requests.post(
                slack_url,
                json={"text": f"Handoff requested: {user_id}\n{case_summary[:1500]}"},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Slack handoff failed: %s", exc)

    if HANDOFF_WEBHOOK_URL:
        try:
            resp = requests.post(
                HANDOFF_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Handoff webhook failed: %s", exc)

    if HANDOFF_EMAIL:
        logger.info("Handoff email notification for %s -> %s", user_id, HANDOFF_EMAIL)
        return True

    return False
