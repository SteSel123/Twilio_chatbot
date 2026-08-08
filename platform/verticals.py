"""Vertical industry config — B2B landing variants and setup preview."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from config import BASE_DIR

VERTICALS_PATH = BASE_DIR / "data" / "verticals.json"

VERTICAL_SLUGS = ("industrial", "construction", "logistics", "financial", "property")


@lru_cache(maxsize=1)
def load_verticals() -> dict[str, dict]:
    if not VERTICALS_PATH.is_file():
        return {}
    data = json.loads(VERTICALS_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def is_vertical(industry: str) -> bool:
    return industry.lower() in load_verticals()


def infer_vertical_from_specialization(specialization: str) -> str | None:
    s = specialization.lower()
    for slug, cfg in load_verticals().items():
        keywords = cfg.get("keywords") or []
        if any(kw in s for kw in keywords):
            return slug
    return None


def get_vertical(industry: str) -> dict | None:
    return load_verticals().get(industry.lower())


def vertical_demo_id(industry: str) -> str | None:
    cfg = get_vertical(industry)
    return cfg.get("demo_id") if cfg else None


def vertical_default_business(industry: str) -> tuple[str, str] | None:
    cfg = get_vertical(industry)
    if not cfg:
        return None
    pair = cfg.get("default_business") or []
    if len(pair) >= 2:
        return str(pair[0]), str(pair[1])
    return None
