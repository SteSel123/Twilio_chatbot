"""Multi-language support (English and Dutch)."""

from __future__ import annotations

import re

NL_MARKERS = re.compile(
    r"\b(hallo|hoi|dag|dank|bedankt|ik wil|naar belgi|naar nederland|"
    r"visum|verblijfsvergunning|immigratie|help me|wat moet ik)\b",
    re.I,
)


def detect_language(message: str) -> str:
    lower = message.lower()
    if NL_MARKERS.search(lower):
        return "nl"
    dutch_words = sum(1 for w in ("de", "het", "een", "van", "naar", "ik", "mijn") if f" {w} " in f" {lower} ")
    english_words = sum(1 for w in ("the", "to", "my", "i", "want", "need") if f" {w} " in f" {lower} ")
    if dutch_words > english_words + 1:
        return "nl"
    return "en"


def t(key: str, lang: str = "en", **kwargs) -> str:
    strings = {
        "welcome": {
            "en": (
                "Hi! I'm here to help you.\n\n"
                "Ask about our services, bookings, pricing, or opening hours."
            ),
            "nl": (
                "Hoi! Ik help je graag.\n\n"
                "Vraag over onze diensten, reserveringen, prijzen of openingstijden."
            ),
        },
        "ack": {
            "en": "Got it — I'm working on your answer, give me about a minute.",
            "nl": "Begrepen — ik werk aan je antwoord, geef me ongeveer een minuut.",
        },
        "feedback_prompt": {
            "en": "\n\n_Was this helpful? Reply 1 (yes) or 2 (no)._",
            "nl": "\n\n_Was dit nuttig? Antwoord 1 (ja) of 2 (nee)._",
        },
        "handoff": {
            "en": "I've notified a human advisor. They will contact you within 1 business day.",
            "nl": "Ik heb een adviseur ingeschakeld. Je wordt binnen 1 werkdag gecontacteerd.",
        },
        "gdpr_export": {
            "en": "Your data export is ready. Check your messages for a summary.",
            "nl": "Je gegevensexport is klaar. Bekijk je berichten voor een samenvatting.",
        },
        "gdpr_delete": {
            "en": "All your data has been deleted. Reply YES to start fresh.",
            "nl": "Al je gegevens zijn verwijderd. Antwoord JA om opnieuw te beginnen.",
        },
        "disclaimer": {
            "en": "_Automated customer service — verify important details with the business._",
            "nl": "_Geautomatiseerde klantenservice — controleer belangrijke details bij het bedrijf._",
        },
    }
    text = strings.get(key, {}).get(lang, strings.get(key, {}).get("en", key))
    return text.format(**kwargs) if kwargs else text


def localized_system_prompt_addendum(lang: str) -> str:
    if lang == "nl":
        return "\n\nIMPORTANT: Respond in Dutch (Nederlands) unless the user writes in English."
    return "\n\nIMPORTANT: Respond in English unless the user writes in Dutch."
