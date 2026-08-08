"""Merge Kaggle-derived sector FAQs into agent preview and seed docs."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from config import BASE_DIR

logger = logging.getLogger(__name__)

KAGGLE_FAQ_PATH = BASE_DIR / "data" / "kaggle_faqs.json"


@lru_cache(maxsize=1)
def load_kaggle_faqs() -> dict[str, list[dict]]:
    if not KAGGLE_FAQ_PATH.is_file():
        return {}
    try:
        data = json.loads(KAGGLE_FAQ_PATH.read_text(encoding="utf-8"))
        return {k.lower(): v for k, v in data.items() if isinstance(v, list)}
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load Kaggle FAQs: %s", exc)
        return {}


def merged_faq_entries(industry: str) -> list[dict]:
    """Industry FAQs + Kaggle supplements (deduped by question)."""
    from platform.industry_faqs import _load_faq_data

    key = (industry or "services").strip().lower()
    base = list(_load_faq_data().get(key, []))
    extra = list(load_kaggle_faqs().get(key, []))
    seen = {str(e.get("question", "")).strip().lower() for e in base}
    for entry in extra:
        q = str(entry.get("question", "")).strip()
        if q and q.lower() not in seen:
            base.append(entry)
            seen.add(q.lower())
    return base
