"""Logging, PII redaction, tracing, SIEM events (WC-51, WC-53, WC-54, WC-58)."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Any

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
_trace_spans: list[dict[str, Any]] = []
_security_events: list[dict[str, Any]] = []

PII_PATTERNS = (
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b"), "[EMAIL]"),
    (re.compile(r"\b\+?\d{9,15}\b"), "[PHONE]"),
    (re.compile(r"\bpassport\s*[:#]?\s*[A-Z0-9]{6,12}\b", re.I), "passport:[REDACTED]"),
)

logger = logging.getLogger("platform.observability")


def new_correlation_id() -> str:
    cid = str(uuid.uuid4())[:8]
    correlation_id_var.set(cid)
    return cid


def redact_pii(text: str) -> str:
    redacted = text
    for pattern, repl in PII_PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted


def log_structured(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "correlation_id": correlation_id_var.get(),
        **{k: redact_pii(str(v)) if isinstance(v, str) else v for k, v in fields.items()},
    }
    logger.info(json.dumps(payload, default=str))


def start_span(name: str) -> str:
    span_id = str(uuid.uuid4())[:8]
    _trace_spans.append({"span_id": span_id, "name": name, "start": time.time()})
    return span_id


def end_span(span_id: str) -> None:
    for span in _trace_spans:
        if span["span_id"] == span_id:
            span["duration_ms"] = int((time.time() - span["start"]) * 1000)
            break


def emit_security_event(event_type: str, severity: str, detail: str) -> None:
    evt = {
        "type": event_type,
        "severity": severity,
        "detail": redact_pii(detail),
        "correlation_id": correlation_id_var.get(),
        "ts": time.time(),
    }
    _security_events.append(evt)
    log_structured("siem_event", **evt)


def detect_anomaly(tenant_id: str, message_count: int) -> None:
    if message_count > 25:
        emit_security_event("rate_anomaly", "warning", f"High volume tenant={tenant_id} count={message_count}")
