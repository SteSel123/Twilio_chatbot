"""Deep health checks for production readiness."""

from __future__ import annotations

import logging

import requests

from config import (
    DATABASE_URL,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OPENAI_API_KEY,
    REDIS_URL,
    TWILIO_ACCOUNT_SID,
    USE_POSTGRES,
)
from platform.redis_client import redis_available

logger = logging.getLogger(__name__)


def check_redis() -> dict:
    if not redis_available():
        return {"status": "degraded", "detail": "Redis unavailable"}
    return {"status": "ok"}


def check_database() -> dict:
    if USE_POSTGRES:
        try:
            import psycopg2

            conn = psycopg2.connect(DATABASE_URL)
            conn.close()
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "fail", "detail": str(exc)}
    return {"status": "ok", "detail": "sqlite (dev)"}


def check_llm() -> dict:
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            return {"status": "fail", "detail": "OPENAI_API_KEY not set"}
        return {"status": "ok", "provider": "openai"}
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.ok:
            return {"status": "ok", "provider": "ollama"}
        return {"status": "degraded", "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"status": "fail", "detail": str(exc)}


def check_twilio() -> dict:
    if not TWILIO_ACCOUNT_SID:
        return {"status": "degraded", "detail": "Twilio not configured"}
    return {"status": "ok"}


def readiness_report() -> dict:
    checks = {
        "redis": check_redis(),
        "database": check_database(),
        "llm": check_llm(),
        "twilio": check_twilio(),
    }
    statuses = [c["status"] for c in checks.values()]
    overall = "ok"
    if "fail" in statuses:
        overall = "fail"
    elif "degraded" in statuses:
        overall = "degraded"
    return {"status": overall, "checks": checks}
