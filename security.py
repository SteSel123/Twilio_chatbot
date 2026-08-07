"""Input sanitization and SSRF protections."""

from __future__ import annotations

import re
from urllib.parse import urlparse

MAX_MESSAGE_LENGTH = 4000
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

ALLOWED_MEDIA_HOSTS = (
    "api.twilio.com",
    "media.twiliocdn.com",
)


def sanitize_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Strip control characters and cap message length."""
    cleaned = CONTROL_CHARS.sub("", text).strip()
    if len(cleaned) > max_length:
        return cleaned[:max_length]
    return cleaned


def encode_outbound_text(text: str) -> str:
    """Plain-text WhatsApp messages — strip control chars only."""
    return sanitize_text(text, max_length=1600)


def is_allowed_media_url(url: str) -> bool:
    """SSRF guard: only allow Twilio-hosted media URLs."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_MEDIA_HOSTS)
