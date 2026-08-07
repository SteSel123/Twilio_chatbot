"""Tests for commercial tone helpers."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from platform.commercial_tone import (
    commercial_opening_answer,
    commercialize_sector_answer,
    is_closed_hours_message,
)

ENERGY_PANEL_ANSWER = (
    "Dat hangt af van je dak, verbruik en gewenst aantal panelen. "
    "Stuur je adres en een recente elektriciteitsfactuur door — "
    "dan plannen we graag een gratis plaatsbezoek met een indicatieve offerte."
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
            business_name="Test Shop",
            industry="restaurant",
            weekday_descriptions=descriptions,
        )
    assert "gesloten" in answer.lower()
    assert "wij bij Test Shop" in answer
    assert "zaterdag" in answer.lower()
    assert "reserveren" in answer.lower()


def test_commercial_opening_open_no_sales_pitch():
    energy = commercial_opening_answer(
        today_summary="Vandaag zijn we open: 09:00–17:00 uur.",
        business_name="EWS Energy",
        industry="energy",
    )
    assert "wij bij EWS Energy" in energy
    assert "open van 09:00 tot 17:00" in energy
    assert "offerte" not in energy.lower()
    assert "gegevens door" not in energy.lower()

    restaurant = commercial_opening_answer(
        today_summary="Vandaag zijn we open: 09:00–18:00 uur.",
        business_name="De Gouden Lepel",
        industry="restaurant",
    )
    assert "wij bij De Gouden Lepel" in restaurant
    assert "09:00" in restaurant
    assert "welkom" in restaurant.lower()
    assert "reserveren" not in restaurant.lower()


def test_commercialize_sector_answer_adds_soft_nudge_when_needed():
    answer = commercialize_sector_answer(
        "Ja, we hebben meerdere vegetarische opties op het menu.",
        "restaurant",
        business_name="De Gouden Lepel",
    )
    assert "vegetarische" in answer.lower()
    assert "langskomen" in answer.lower() or "wil je" in answer.lower()


def test_commercialize_sector_answer_no_duplicate_on_energy_faq():
    answer = commercialize_sector_answer(ENERGY_PANEL_ANSWER, "energy")
    assert answer.count("plaatsbezoek") == 1
    assert answer.count("Zal ik") == 0
    assert "Wil je" not in answer


def test_commercialize_sector_answer_skips_when_question_present():
    original = "Voor knippen raden we 1–2 weken van tevoren aan. Zal ik een plek voor je zoeken?"
    answer = commercialize_sector_answer(original, "salon")
    assert answer == original
