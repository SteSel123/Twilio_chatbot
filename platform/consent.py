"""GDPR consent flow for first-time users."""

from __future__ import annotations

from config import PRIVACY_POLICY_URL, TERMS_URL


CONSENT_KEYWORDS = {"yes", "agree", "i agree", "accept", "ok", "okay", "ja", "akkoord", "oui"}
PRIVACY_VERSION = "1.0"


def consent_message(lang: str = "en", business_name: str = "this business") -> str:
    privacy = PRIVACY_POLICY_URL or "/privacy"
    terms = TERMS_URL or "/terms"
    if lang == "nl":
        return (
            f"Welkom bij {business_name}!\n\n"
            "Voordat we beginnen:\n"
            "• Dit is geautomatiseerde klantenservice — geen medisch/juridisch advies tenzij anders vermeld.\n"
            "• Je gegevens worden tijdelijk opgeslagen om je te helpen.\n"
            "• Typ 'export my data' of 'delete my data' voor GDPR-verzoeken.\n\n"
            f"Privacy: {privacy}\nVoorwaarden: {terms}\n\n"
            "Antwoord *JA* om door te gaan."
        )
    return (
        f"Welcome to {business_name}!\n\n"
        "Before we start:\n"
        "• This is automated customer service — not professional legal/medical advice unless stated.\n"
        "• Your data is stored temporarily to help you.\n"
        "• Type 'export my data' or 'delete my data' for GDPR requests.\n\n"
        f"Privacy: {privacy}\nTerms: {terms}\n\n"
        "Reply *YES* to continue."
    )


def is_consent_response(message: str) -> bool:
    return message.strip().lower() in CONSENT_KEYWORDS


def has_consent(store, scoped_user_id: str) -> bool:
    if hasattr(store, "has_consent"):
        return store.has_consent(scoped_user_id)
    return True  # SQLite dev mode — no consent table


def record_consent(store, scoped_user_id: str) -> None:
    if hasattr(store, "record_consent"):
        store.record_consent(scoped_user_id, PRIVACY_VERSION)
