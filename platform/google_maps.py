"""Google Maps / Places API — opening hours, address, and links for preview + live agent."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import requests

from config import GOOGLE_MAPS_API_KEY

if TYPE_CHECKING:
    from platform.business_profile import BusinessProfile

logger = logging.getLogger(__name__)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_TZ = ZoneInfo("Europe/Brussels")
_MAPS_CACHE_TTL_SECONDS = 3600
_maps_cache: dict[str, tuple[float, dict[str, Any]]] = {}

MAPS_QUERY_PATTERN = re.compile(
    r"\b("
    r"openingstijden|openingsuren|openings?tijd|"
    r"hoe\s+laat|wanneer\s+(open|gesloten)|"
    r"\bopen\b|\bgesloten\b|\bhours\b|"
    r"adres|address|locatie|location|"
    r"waar\s+(zitten|vinden|is|zit)|"
    r"route|routebeschrijving|directions|"
    r"google\s*maps|\bmaps\b|"
    r"website|url|link|navigatie"
    r")\b",
    re.I,
)

WEEKDAY_NL = (
    "maandag",
    "dinsdag",
    "woensdag",
    "donderdag",
    "vrijdag",
    "zaterdag",
    "zondag",
)


def _normalize_hours_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("–", "–").strip())


def _today_weekday_index() -> int:
    return datetime.now(DEFAULT_TZ).weekday()


def _pick_today_from_weekday_descriptions(descriptions: list[str]) -> str:
    """Match today's Dutch/English weekday label from Google weekdayDescriptions."""
    today_idx = _today_weekday_index()
    today_nl = WEEKDAY_NL[today_idx]
    today_en = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )[today_idx]

    for line in descriptions:
        lower = line.lower()
        if lower.startswith(today_nl) or lower.startswith(today_en):
            return _normalize_hours_text(line)
    if descriptions:
        return _normalize_hours_text(descriptions[today_idx % len(descriptions)])
    return ""


def _format_today_summary(
    *,
    weekday_descriptions: list[str],
    open_now: bool | None,
) -> str:
    today_line = _pick_today_from_weekday_descriptions(weekday_descriptions)
    if today_line:
        # Strip leading "Vrijdag: " etc. for natural answer
        hours_part = re.sub(r"^[A-Za-zÀ-ÿ]+:\s*", "", today_line).strip()
        closed_markers = ("gesloten", "closed", "24 hours closed")
        if any(m in today_line.lower() for m in closed_markers):
            return "Vandaag zijn we gesloten."
        if hours_part:
            return f"Vandaag zijn we open: {hours_part}."
    if open_now is True:
        return "Vandaag zijn we nu open."
    if open_now is False:
        return "Vandaag zijn we momenteel gesloten."
    return ""


def fetch_google_maps_hours(
    business_query: str,
    city: str = "",
) -> dict[str, Any]:
    """
    Look up opening hours via Google Places API (Maps data).
    Returns empty dict when API key missing or no place found.
    """
    api_key = GOOGLE_MAPS_API_KEY.strip()
    if not api_key:
        logger.info("Google Maps lookup skipped — GOOGLE_MAPS_API_KEY not set")
        return {}

    text_query = f"{business_query} {city}".strip()
    try:
        resp = requests.post(
            PLACES_SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": (
                    "places.displayName,places.formattedAddress,"
                    "places.regularOpeningHours,places.currentOpeningHours,"
                    "places.googleMapsUri,places.websiteUri,places.businessStatus"
                ),
            },
            json={"textQuery": text_query, "languageCode": "nl", "regionCode": "BE"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Google Maps Places lookup failed: %s", exc)
        return {}

    places = data.get("places") or []
    if not places:
        return {}

    place = places[0]
    display_name = (place.get("displayName") or {}).get("text", business_query)
    address = place.get("formattedAddress", "")
    maps_uri = place.get("googleMapsUri", "")
    website_uri = place.get("websiteUri", "")

    regular = place.get("regularOpeningHours") or {}
    current = place.get("currentOpeningHours") or {}
    weekday_descriptions = [
        _normalize_hours_text(str(line))
        for line in (regular.get("weekdayDescriptions") or [])
        if str(line).strip()
    ]

    open_now = current.get("openNow")
    if open_now is None:
        open_now = regular.get("openNow")

    today_summary = _format_today_summary(
        weekday_descriptions=weekday_descriptions,
        open_now=open_now,
    )

    return {
        "display_name": display_name,
        "address": address,
        "google_maps_uri": maps_uri,
        "website_uri": website_uri,
        "weekday_descriptions": weekday_descriptions,
        "opening_hours_today": today_summary,
        "open_now": open_now,
    }


def message_needs_google_maps(message: str) -> bool:
    """True when the customer asks about hours, address, or location links."""
    return bool(MAPS_QUERY_PATTERN.search(message or ""))


def _cache_key(tenant_id: str, business_name: str, city: str) -> str:
    return f"{tenant_id}|{business_name.strip().lower()}|{city.strip().lower()}"


def fetch_google_maps_for_profile(profile: BusinessProfile) -> dict[str, Any]:
    """Cached Google Maps lookup for a tenant business profile."""
    key = _cache_key(profile.tenant_id, profile.business_name, profile.business_city)
    now = time.time()
    cached = _maps_cache.get(key)
    if cached and now - cached[0] < _MAPS_CACHE_TTL_SECONDS:
        return cached[1]

    maps = fetch_google_maps_hours(profile.business_name, city=profile.business_city)
    if maps:
        _maps_cache[key] = (now, maps)
    return maps


def format_maps_agent_context(maps: dict[str, Any]) -> str:
    """Compact Google Maps block for live WhatsApp LLM context."""
    if not maps:
        return ""

    lines = [
        "## Google Maps (bron van waarheid voor openingstijden, adres en locatie-link)",
        "Gebruik uitsluitend onderstaande gegevens voor openingstijden, adres, route en links.",
    ]
    if maps.get("display_name"):
        lines.append(f"- **Bedrijf:** {maps['display_name']}")
    if maps.get("address"):
        lines.append(f"- **Adres:** {maps['address']}")
    if maps.get("google_maps_uri"):
        lines.append(f"- **Google Maps URL:** {maps['google_maps_uri']}")
    if maps.get("website_uri"):
        lines.append(f"- **Website URL:** {maps['website_uri']}")
    for desc in maps.get("weekday_descriptions") or []:
        lines.append(f"- {desc}")
    if maps.get("opening_hours_today"):
        lines.append(f"- **Vandaag:** {maps['opening_hours_today']}")
    return "\n".join(lines)


def get_maps_context_for_profile(profile: BusinessProfile) -> str:
    """Fetch + format Google Maps context for the live agent."""
    return format_maps_agent_context(fetch_google_maps_for_profile(profile))


def format_maps_hours_knowledge(maps: dict[str, Any]) -> str:
    """Markdown block for tenant knowledge + preview hour parsing."""
    if not maps.get("weekday_descriptions") and not maps.get("opening_hours_today"):
        return ""

    lines = ["## Google Maps — Openingstijden"]
    name = maps.get("display_name")
    if name:
        lines.append(f"- **Bedrijf:** {name}")
    if maps.get("address"):
        lines.append(f"- **Adres:** {maps['address']}")
    for desc in maps.get("weekday_descriptions") or []:
        lines.append(f"- {desc}")
    if maps.get("opening_hours_today"):
        lines.append(f"- **Vandaag:** {maps['opening_hours_today']}")
    if maps.get("google_maps_uri"):
        lines.append(f"- **Google Maps URL:** {maps['google_maps_uri']}")
    if maps.get("website_uri"):
        lines.append(f"- **Website URL:** {maps['website_uri']}")
    if maps.get("google_maps_uri") or maps.get("website_uri"):
        lines.append("- **Bron:** Google Maps")
    return "\n".join(lines)
