"""Generic patterns for SMB customer message parsing."""

from __future__ import annotations

import re

# Common service / intent keywords (industry-agnostic)
SERVICE_TRIGGERS = (
    "book", "booking", "appointment", "schedule", "reserve", "reservation",
    "price", "pricing", "cost", "quote", "estimate", "how much",
    "hours", "open", "closed", "location", "address", "directions",
    "menu", "service", "product", "order", "delivery", "pickup",
    "help", "support", "question", "info", "information",
    "cancel", "refund", "return", "complaint",
)

TOPIC_PATTERN = re.compile(
    r"\b(booking|appointment|order|delivery|quote|pricing|hours|location|"
    r"menu|service|product|support|refund|cancel|membership|subscription)\b",
    re.I,
)

SERVICE_TYPE_PATTERN = re.compile(
    r"\b(standard|premium|basic|consultation|installation|repair|"
    r"delivery|takeaway|dine-in|pickup|walk-in|online)\b",
    re.I,
)

# Legacy aliases for backward compatibility during migration
COUNTRY_PATTERN = TOPIC_PATTERN
PROCESS_PATTERN = SERVICE_TYPE_PATTERN
IMMIGRATION_TRIGGERS = SERVICE_TRIGGERS
