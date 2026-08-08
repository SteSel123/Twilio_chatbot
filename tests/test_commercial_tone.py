"""Tests for commercial tone helpers."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from platform.commercial_tone import (
    commercial_opening_answer,
    commercialize_sector_answer,
    is_closed_hours_message,
)


def test_is_closed_hours_message():
    assert is_closed_hours_message("Vandaag zijn we gesloten.")
    assert is_closed_hours_message("Closed today")
    assert not is_closed_hours_message("Vandaag zijn we open: 09:00–18:00.")


def test_commercial_opening_closed_ends_with_alternative_and_soft_cta():
    descriptions = [
        "maandag: 08:00–20:00 uur",
        "dinsdag: 08:00–20:00 uur",
        "woensdag: 08:00–20:00 uur",
        "donderdag: 08:00–20:00 uur",
        "vrijdag: 08:00–20:00 uur",
        "zaterdag: 10:00–16:00 uur",
        "zondag: Gesloten",
    ]
    with patch("platform.commercial_tone.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 8, 7, 12, 0, tzinfo=ZoneInfo("Europe/Brussels"))
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        answer = commercial_opening_answer(
            today_summary="Vandaag zijn we gesloten.",
            business_name="TechServ Industrial",
            industry="industrial",
            weekday_descriptions=descriptions,
        )
    assert "gesloten" in answer.lower()
    assert "wij bij TechServ Industrial" in answer
    assert "zaterdag" in answer.lower()
    assert "storings" in answer.lower() or "onderhoud" in answer.lower()


def test_commercial_opening_open_no_sales_pitch():
    industrial = commercial_opening_answer(
        today_summary="Vandaag zijn we open: 09:00–17:00 uur.",
        business_name="TechServ Industrial",
        industry="industrial",
    )
    assert "wij bij TechServ Industrial" in industrial
    assert "open van 09:00 tot 17:00" in industrial
    assert "offerte" not in industrial.lower()

    construction = commercial_opening_answer(
        today_summary="Vandaag zijn we open: 09:00–18:00 uur.",
        business_name="InstallPro BV",
        industry="construction",
    )
    assert "wij bij InstallPro BV" in construction
    assert "09:00" in construction
    assert "intake" in construction.lower() or "helpen" in construction.lower()


def test_commercialize_sector_answer_adds_soft_nudge_when_needed():
    answer = commercialize_sector_answer(
        "Ja, storingsdienst is 24/7 bereikbaar.",
        "industrial",
        business_name="TechServ Industrial",
    )
    assert "storingsdienst" in answer.lower()
    assert "monteur" in answer.lower() or "wil je" in answer.lower()


def test_commercialize_sector_answer_no_duplicate_on_construction_faq():
    original = (
        "Meestal binnen 5 werkdagen. Stuur je adres door — "
        "dan plannen we een gratis technische intake in."
    )
    answer = commercialize_sector_answer(original, "construction")
    assert answer.count("intake") == 1
    assert answer.count("Zal ik") == 0


def test_commercialize_sector_answer_skips_when_question_present():
    original = "Voor knippen raden we 1–2 weken van tevoren aan. Zal ik een plek voor je zoeken?"
    answer = commercialize_sector_answer(original, "construction")
    assert answer == original
