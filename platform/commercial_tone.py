"""Commercial tone — human first; sell only when it fits the question."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("Europe/Brussels")

WEEKDAY_NL = (
    "maandag",
    "dinsdag",
    "woensdag",
    "donderdag",
    "vrijdag",
    "zaterdag",
    "zondag",
)

CLOSED_MARKERS = ("gesloten", "closed", "24 hours closed")

# When open: just be friendly — no sales pitch on a hours question.
_OPEN_CLOSING: dict[str, str] = {
    "restaurant": "Je bent van harte welkom!",
    "salon": "Tot snel!",
    "retail": "We zien je graag!",
    "healthcare": "Tot snel!",
    "energy": "Tot ziens!",
    "services": "Tot ziens!",
}

# When closed: alternative first; soft CTA only for visit-oriented sectors.
_CLOSED_SOFT_CTA: dict[str, str] = {
    "restaurant": "Zal ik alvast iets voor je reserveren?",
    "salon": "Zal ik een moment voor je vastleggen?",
    "retail": "Wil je dat ik het voor je klaarleg?",
    "healthcare": "Zal ik een afspraak voor je inplannen?",
    "energy": "Stuur gerust een berichtje — dan plannen we een geschikt moment.",
    "services": "Stuur gerust je vraag door — we nemen het snel op.",
}

# Extra nudge only when sector FAQ is purely informational (no next step yet).
_SOFT_SECTOR_NUDGE: dict[str, str] = {
    "restaurant": "Wil je vanavond langskomen?",
    "salon": "Wil je dat ik een plek voor je zoek?",
    "retail": "Kom gerust langs als je wilt kijken.",
    "healthcare": "Wil je dat ik een afspraak voorstel?",
    "energy": "Wil je dat we een kort plaatsbezoek inplannen?",
    "services": "Wil je dat we een moment inplannen?",
}


def is_closed_hours_message(text: str) -> bool:
    lower = (text or "").lower()
    return any(m in lower for m in CLOSED_MARKERS)


def _next_open_day_hint(weekday_descriptions: list[str] | None) -> str:
    """Find next non-closed day from Google Maps weekday lines."""
    lines = weekday_descriptions or []
    if not lines:
        return "We zijn binnenkort weer open — stuur gerust een berichtje."

    today_idx = datetime.now(DEFAULT_TZ).weekday()
    for offset in range(1, 8):
        idx = (today_idx + offset) % 7
        if idx >= len(lines):
            continue
        line = lines[idx]
        lower = line.lower()
        if any(m in lower for m in CLOSED_MARKERS):
            continue
        hours = re.sub(r"^[A-Za-zÀ-ÿ]+:\s*", "", line).strip()
        day_label = line.split(":")[0].strip() if ":" in line else WEEKDAY_NL[idx].capitalize()
        if hours:
            return f"{day_label.capitalize()} zijn we weer open ({hours})."
        return f"{day_label.capitalize()} zijn we weer open."

    return "Stuur ons gerust een berichtje — dan kijken we wanneer het past."


def _normalize_today_summary(today_summary: str) -> str:
    today = (today_summary or "").strip().rstrip(".")
    if not today:
        return ""
    if not today.lower().startswith("vandaag"):
        if is_closed_hours_message(today):
            return "Vandaag zijn we gesloten"
        return f"Vandaag zijn we open: {today}"
    return today


def _parse_today_hours(today_summary: str) -> tuple[bool | None, str]:
    """Return (closed?, hours_text) from a today summary line."""
    today = (today_summary or "").strip()
    if not today:
        return None, ""
    if is_closed_hours_message(today):
        return True, ""
    match = re.search(r"open:\s*(.+?)(?:\.|$)", today, re.I)
    if match:
        return False, match.group(1).strip().rstrip(".")
    if re.search(r"\d{1,2}:\d{2}", today):
        cleaned = re.sub(r"^vandaag\s+(?:zijn we )?open:?\s*", "", today, flags=re.I).strip()
        return False, cleaned.rstrip(".")
    return None, today.rstrip(".")


def _format_hours_for_speech(hours: str) -> str:
    """Turn '09:00–18:00 uur' into natural Dutch '09:00 tot 18:00 uur'."""
    text = (hours or "").strip().rstrip(".")
    text = re.sub(r"\s*[-–—]\s*", " tot ", text)
    return text


def commercial_opening_answer(
    *,
    today_summary: str,
    business_name: str,
    industry: str,
    weekday_descriptions: list[str] | None = None,
) -> str:
    """Opening-hours reply — personal tone with business name; CTA only when closed."""
    industry_key = (industry or "services").lower()
    today = _normalize_today_summary(today_summary)
    name = business_name.strip() or "ons"

    if not today:
        return (
            f"Hoi! Bij {name} helpen we je graag. "
            "Ik heb de openingstijden nu niet meteen paraat — stuur gerust je vraag door."
        )

    closed, hours = _parse_today_hours(today)

    if closed is True or is_closed_hours_message(today):
        alternative = _next_open_day_hint(weekday_descriptions)
        soft = _CLOSED_SOFT_CTA.get(industry_key, _CLOSED_SOFT_CTA["services"])
        return (
            f"Ja, wij bij {name} zijn vandaag gesloten. {alternative} {soft}"
        )

    if hours:
        hours_spoken = _format_hours_for_speech(hours)
        closing = _OPEN_CLOSING.get(industry_key, _OPEN_CLOSING["services"])
        return f"Ja, wij bij {name} zijn vandaag open van {hours_spoken}. {closing}"

    closing = _OPEN_CLOSING.get(industry_key, _OPEN_CLOSING["services"])
    return f"Ja, wij bij {name} zijn vandaag open. {closing}"


def _answer_already_has_next_step(text: str) -> bool:
    """True when the FAQ answer already invites action — avoid double CTAs."""
    lower = text.lower()
    markers = (
        "zal ik",
        "wil je",
        "wil u",
        "stuur je",
        "stuur ons",
        "stuur uw",
        "bel ons",
        "bel gerust",
        "plannen we",
        "planning",
        "afspraak",
        "reserver",
        "offerte",
        "plaatsbezoek",
        "langskomen",
        "vastleg",
        "doorgeven",
        "neem contact",
        "koppelen we",
    )
    return any(m in lower for m in markers)


def commercialize_sector_answer(
    answer: str,
    industry: str,
    *,
    business_name: str = "",
) -> str:
    """Light commercial nudge only when the sector answer has no next step yet."""
    text = (answer or "").strip()
    if not text:
        return text

    if _answer_already_has_next_step(text):
        return text

    industry_key = (industry or "services").lower()
    nudge = _SOFT_SECTOR_NUDGE.get(industry_key, _SOFT_SECTOR_NUDGE["services"])
    base = text.rstrip(".")
    return f"{base}. {nudge}"
