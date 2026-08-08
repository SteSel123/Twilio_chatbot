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

_OPEN_CLOSING: dict[str, str] = {
    "industrial": "We helpen je graag verder!",
    "construction": "Tot de intake op locatie!",
    "logistics": "We sturen je meteen de status door!",
    "financial": "Tot snel!",
    "property": "We houden je op de hoogte!",
    "services": "Tot ziens!",
}

_CLOSED_SOFT_CTA: dict[str, str] = {
    "industrial": "Zal ik alvast een storings- of onderhoudsmoment voorstellen?",
    "construction": "Zal ik een intake op locatie voor je inplannen?",
    "logistics": "Wil je dat ik een ophaalmoment of ETA-bevestiging stuur?",
    "financial": "Zal ik een afspraak of documentchecklist sturen?",
    "property": "Zal ik een technieker of bezichtiging voor je inplannen?",
    "services": "Stuur gerust je vraag door — we nemen het snel op.",
}

_SOFT_SECTOR_NUDGE: dict[str, str] = {
    "industrial": "Wil je dat we de monteur definitief inplannen?",
    "construction": "Wil je dat we de intake op locatie vastleggen?",
    "logistics": "Wil je dat ik de zending meteen reserveer?",
    "financial": "Wil je dat we een kort gesprek inplannen?",
    "property": "Wil je dat ik de technieker bevestig?",
    "services": "Wil je dat we een moment inplannen?",
}


def is_closed_hours_message(text: str) -> bool:
    lower = (text or "").lower()
    return any(m in lower for m in CLOSED_MARKERS)


def _next_open_day_hint(weekday_descriptions: list[str] | None, locale: str = "nl") -> str:
    from platform.preview_i18n import normalize_locale, pt

    loc = normalize_locale(locale)
    lines = weekday_descriptions or []
    if not lines:
        return pt("next_open_fallback", loc)

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
            return pt("next_open_day", loc, day=day_label.capitalize(), hours=hours)
        return pt("next_open_day_simple", loc, day=day_label.capitalize())

    return pt("next_open_fallback", loc)


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


def _format_hours_for_speech(hours: str, locale: str = "nl") -> str:
    from platform.preview_i18n import normalize_locale

    loc = normalize_locale(locale)
    text = (hours or "").strip().rstrip(".")
    separator = {
        "nl": " tot ",
        "en": " to ",
        "fr": " à ",
        "es": " a ",
        "it": " alle ",
        "de": " bis ",
    }.get(loc, " to ")
    text = re.sub(r"\s*[-–—]\s*", separator, text)
    return text


def commercial_opening_answer(
    *,
    today_summary: str,
    business_name: str,
    industry: str,
    weekday_descriptions: list[str] | None = None,
    locale: str = "nl",
) -> str:
    from platform.preview_i18n import industry_copy, normalize_locale, pt

    industry_key = (industry or "construction").lower()
    loc = normalize_locale(locale)
    today = _normalize_today_summary(today_summary)
    name = business_name.strip() or pt("us_fallback", loc)

    if not today:
        return pt("opening_no_hours_online", loc, business=name)

    closed, hours = _parse_today_hours(today)

    if closed is True or is_closed_hours_message(today):
        alternative = _next_open_day_hint(weekday_descriptions, loc)
        soft = industry_copy("closed_cta", industry_key, loc)
        return pt("opening_closed", loc, business=name, next_open=alternative, soft_cta=soft)

    closing = industry_copy("open_closing", industry_key, loc)
    if hours:
        hours_spoken = _format_hours_for_speech(hours, loc)
        return pt("opening_open_hours", loc, business=name, hours=hours_spoken, closing=closing)

    return pt("opening_open_today", loc, business=name, closing=closing)


def _answer_already_has_next_step(text: str) -> bool:
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
    text = (answer or "").strip()
    if not text:
        return text

    if _answer_already_has_next_step(text):
        return text

    industry_key = (industry or "construction").lower()
    nudge = _SOFT_SECTOR_NUDGE.get(industry_key, _SOFT_SECTOR_NUDGE["services"])
    base = text.rstrip(".")
    return f"{base}. {nudge}"
