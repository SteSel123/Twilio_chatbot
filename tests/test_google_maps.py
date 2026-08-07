"""Tests for Google Maps opening hours lookup."""

from unittest.mock import MagicMock, patch

from platform.google_maps import (
    fetch_google_maps_hours,
    format_maps_hours_knowledge,
    _format_today_summary,
)


def test_format_today_summary_from_weekday_descriptions():
    descriptions = [
        "maandag: 09:00–18:00 uur",
        "dinsdag: 09:00–18:00 uur",
        "woensdag: 09:00–18:00 uur",
        "donderdag: 09:00–18:00 uur",
        "vrijdag: 09:00–18:00 uur",
        "zaterdag: 10:00–16:00 uur",
        "zondag: Gesloten",
    ]
    summary = _format_today_summary(weekday_descriptions=descriptions, open_now=True)
    assert "Vandaag" in summary


def test_format_maps_hours_knowledge():
    block = format_maps_hours_knowledge(
        {
            "display_name": "Delhaize Halle",
            "address": "Stationsstraat 1, Halle",
            "weekday_descriptions": ["maandag: 08:00–20:00 uur"],
            "opening_hours_today": "Vandaag zijn we open: 08:00–20:00 uur.",
        }
    )
    assert "Google Maps" in block
    assert "Delhaize Halle" in block
    assert "Vandaag" in block


@patch("platform.google_maps.GOOGLE_MAPS_API_KEY", "test-key")
@patch("platform.google_maps.requests.post")
def test_fetch_google_maps_hours(mock_post):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "places": [
            {
                "displayName": {"text": "EWS Energy"},
                "formattedAddress": "Stoofstraat 39b, Merchtem",
                "regularOpeningHours": {
                    "weekdayDescriptions": [
                        "maandag: 09:00–17:00 uur",
                        "dinsdag: 09:00–17:00 uur",
                        "woensdag: 09:00–17:00 uur",
                        "donderdag: 09:00–17:00 uur",
                        "vrijdag: 09:00–17:00 uur",
                        "zaterdag: Gesloten",
                        "zondag: Gesloten",
                    ],
                },
                "currentOpeningHours": {"openNow": True},
                "googleMapsUri": "https://maps.google.com/?cid=123",
                "websiteUri": "https://ewsenergy.be",
            }
        ]
    }
    mock_post.return_value = mock_resp

    out = fetch_google_maps_hours("EWS Energy", city="Merchtem")
    assert out["display_name"] == "EWS Energy"
    assert out["weekday_descriptions"]
    assert out["opening_hours_today"]
    assert "maps.google.com" in out["google_maps_uri"]
    assert out["website_uri"] == "https://ewsenergy.be"


def test_message_needs_google_maps():
    from platform.google_maps import message_needs_google_maps

    assert message_needs_google_maps("Hoe laat zijn jullie vandaag open?")
    assert message_needs_google_maps("Wat is jullie adres?")
    assert message_needs_google_maps("Stuur de Google Maps link")
    assert not message_needs_google_maps("Wat kost een zonnepaneel?")


def test_format_maps_agent_context():
    from platform.google_maps import format_maps_agent_context

    ctx = format_maps_agent_context(
        {
            "display_name": "EWS Energy",
            "address": "Stoofstraat 39b, Merchtem",
            "google_maps_uri": "https://maps.google.com/?cid=123",
            "website_uri": "https://ewsenergy.be",
            "weekday_descriptions": ["vrijdag: 09:00–17:00 uur"],
            "opening_hours_today": "Vandaag zijn we open: 09:00–17:00 uur.",
        }
    )
    assert "Google Maps URL" in ctx
    assert "Website URL" in ctx
    assert "Stoofstraat" in ctx
    assert "bron van waarheid" in ctx.lower()


@patch("platform.google_maps.GOOGLE_MAPS_API_KEY", "")
def test_fetch_skips_without_api_key():
    assert fetch_google_maps_hours("Test", city="Utrecht") == {}
