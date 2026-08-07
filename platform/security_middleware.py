"""HTTPS, WAF patterns, IP allowlist (WC-11, WC-13, WC-15)."""

from __future__ import annotations

import os
import re

from flask import Request, abort

WAF_PATTERNS = (
    re.compile(r"<\s*script", re.I),
    re.compile(r"union\s+select", re.I),
    re.compile(r";\s*drop\s+table", re.I),
    re.compile(r"\.\./"),
)

ALLOWED_IPS = {
    ip.strip()
    for ip in os.getenv("WEBHOOK_ALLOWED_IPS", "").split(",")
    if ip.strip()
}
ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "1") == "1"


def check_request_security(req: Request) -> None:
    if ENFORCE_HTTPS and req.headers.get("X-Forwarded-Proto", req.scheme) not in ("https", ""):
        if req.remote_addr not in ("127.0.0.1", "::1"):
            abort(403, description="HTTPS required")

    if ALLOWED_IPS and req.remote_addr not in ALLOWED_IPS:
        abort(403, description="IP not allowlisted")

    body = req.get_data(as_text=True) or ""
    for pattern in WAF_PATTERNS:
        if pattern.search(body):
            abort(403, description="Request blocked by WAF")
