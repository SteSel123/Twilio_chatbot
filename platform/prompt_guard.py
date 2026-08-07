"""Prompt injection hardening (WC-38)."""

from __future__ import annotations

import re

INJECTION_PATTERNS = (
    re.compile(r"ignore (all )?(previous|prior) instructions", re.I),
    re.compile(r"you are now (a )?", re.I),
    re.compile(r"system:\s*", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
)


def strip_injection_attempts(text: str) -> str:
    cleaned = text
    for pattern in INJECTION_PATTERNS:
        cleaned = pattern.sub("[filtered]", cleaned)
    return cleaned.strip()
