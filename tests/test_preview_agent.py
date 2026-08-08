"""Tests for agentic preview session."""

from unittest.mock import MagicMock, patch

from platform.preview_agent import (
    PreviewTurnResult,
    handle_preview_turn,
    run_opening_hours_preview,
)


class _FakeAgent:
    memory = MagicMock()

    def __init__(self):
        self.data_store = MagicMock()
        self._should_search_web = MagicMock(return_value=False)
        self._build_search_query = MagicMock(return_value="test query")


@patch("platform.preview_agent.generate_response")
@patch("platform.preview_agent.load_all_docs")
@patch("platform.preview_agent.vector_search")
@patch("platform.preview_agent.load_business_profile")
def test_handle_preview_turn_returns_reply(mock_profile, mock_vs, mock_docs, mock_llm):
    mock_profile.return_value = MagicMock(
        industry="industrial",
        language_default="nl",
        docs_dir=MagicMock(),
    )
    mock_docs.return_value = {"doc": "Storingsdienst €95/u"}
    mock_vs.return_value = "Storingsdienst €95/u excl. onderdelen"
    mock_llm.return_value = "Storingsdienst kost €95/u. Stuur serienummer door voor planning vandaag."

    agent = _FakeAgent()
    turn = handle_preview_turn(
        agent,
        tenant_id="t1",
        message="Wat kost storingsdienst?",
    )
    assert isinstance(turn, PreviewTurnResult)
    assert "€95" in turn.reply
    assert turn.traces


@patch("platform.preview_agent.compose_opening_hours_reply")
def test_run_opening_hours_preview(mock_compose):
    mock_compose.return_value = (
        "Ja, wij bij Test zijn vandaag open van 09:00 tot 18:00.",
        [{"kind": "docs", "files": ["Google Maps"]}],
    )
    out = run_opening_hours_preview(
        _FakeAgent(), tenant_id="t1", industry="industrial", business_name="Test"
    )
    assert out["phase"] == "opening_hours"
    assert out["await_upload"] is True
    assert "09:00" in out["sample_answer"]
    mock_compose.assert_called_once()


def test_compose_opening_hours_with_maps_today():
    from platform.preview_agent import compose_opening_hours_reply

    reply, traces = compose_opening_hours_reply(
        business_name="TechServ",
        industry="industrial",
        opening_hours_today="Vandaag zijn we open: 09:00–18:00 uur.",
        google_maps_hours=True,
    )
    assert "09:00" in reply
    assert "18:00" in reply
    assert "stuur je vraag door" not in reply.lower()
    assert traces
    assert "Google Maps" in traces[0]["files"][0] or "openingstijden" in traces[0]["files"][0].lower()


def test_compose_opening_hours_vellemans_style_no_hours_gives_phone():
    from platform.preview_agent import compose_opening_hours_reply

    knowledge = (
        "## Google — Vellemans Halle\n"
        "Centrale verwarming installatie. Contact: 02 356 42 38 · info@vellemans.be"
    )
    reply, _ = compose_opening_hours_reply(
        business_name="Vellemans",
        industry="construction",
        knowledge=knowledge,
        google_maps_hours=False,
    )
    assert "02 356 42 38" in reply or "356" in reply
    assert "stuur je vraag door" not in reply.lower()
    assert "afspraak" in reply.lower() or "bel" in reply.lower()


def test_compose_opening_hours_respects_locale():
    from platform.preview_agent import compose_opening_hours_reply, opening_hours_question

    reply, _ = compose_opening_hours_reply(
        business_name="Fontanero Test",
        industry="construction",
        opening_hours_today="Vandaag zijn we gesloten.",
        weekday_descriptions=["lunes: 08:00–20:00", "martes: 08:00–20:00"],
        google_maps_hours=True,
        locale="es",
    )
    assert "cerrado" in reply.lower()
    assert "gesloten" not in reply.lower()
    assert opening_hours_question("es").lower().startswith("¿")


@patch("platform.preview_agent.handle_preview_turn")
def test_run_upload_follow_up_preview(mock_turn):
    from platform.preview_agent import run_upload_follow_up_preview

    knowledge = (
        "12 zonnepanelen (2550 kWh/jaar) | materiaal: € 2.600 – € 3.000 | "
        "installatie: € 950 tot € 1.100 | totaal: € 3.550 tot € 4.100"
    )
    out = run_upload_follow_up_preview(
        _FakeAgent(),
        tenant_id="t1",
        industry="industrial",
        business_name="Vellemans",
        knowledge=knowledge,
        source_name="zonnepanelen.png",
    )
    assert out["phase"] == "upload"
    assert out["append"] is True
    question = out["sample_question"].lower()
    assert "cnc" not in question
    assert "e47" not in question
    assert "storingsmonteur" not in question
    assert "zonnepanelen" in question or "12 zonnepanelen" in question
    assert "3.550" in out["sample_answer"] or "3550" in out["sample_answer"]
    mock_turn.assert_not_called()


def test_compose_upload_reply_solar():
    from platform.preview_agent import compose_upload_reply

    knowledge = (
        "12 zonnepanelen (2550 kWh/jaar) | materiaal: € 2.600 – € 3.000 | "
        "installatie: € 950 tot € 1.100 | totaal: € 3.550 tot € 4.100"
    )
    result = compose_upload_reply(
        knowledge=knowledge,
        business_name="Vellemans",
        industry="industrial",
        source_name="zonnepanelen.png",
    )
    assert result is not None
    reply, traces = result
    assert "3.550" in reply or "3550" in reply
    assert "12 zonnepanelen" in reply.lower()
    assert traces


@patch("platform.preview_agent.openai_tool_calling_available", return_value=False)
@patch("platform.preview_agent.generate_response")
@patch("platform.preview_agent.load_all_docs")
@patch("platform.preview_agent.vector_search")
@patch("platform.preview_agent.load_business_profile")
def test_handle_preview_turn_uses_upload_knowledge(mock_profile, mock_vs, mock_docs, mock_llm, _mock_tools):
    mock_profile.return_value = MagicMock(
        industry="industrial",
        language_default="nl",
        docs_dir=MagicMock(),
    )
    mock_docs.return_value = {}
    mock_vs.return_value = ""
    mock_llm.return_value = "Antwoord uit upload."

    knowledge = "Storingsdienst — €95/u excl. onderdelen"
    agent = _FakeAgent()
    turn = handle_preview_turn(
        agent,
        tenant_id="t1",
        message="Wat kost storingsdienst?",
        upload_source=True,
        upload_knowledge=knowledge,
        source_name="tarieven.png",
    )
    mock_vs.assert_not_called()
    assert turn.reply == "Antwoord uit upload."
    internal = mock_llm.call_args.kwargs["internal_context"]
    assert "€95" in internal


def test_run_calendar_booking_preview():
    from platform.preview_agent import run_calendar_booking_preview

    knowledge = "12 zonnepanelen | totaal: € 3.550 tot € 4.100"
    out = run_calendar_booking_preview(
        _FakeAgent(),
        tenant_id="t1",
        industry="industrial",
        business_name="Vellemans",
        knowledge=knowledge,
        google_connected=False,
    )
    assert out["phase"] == "calendar"
    assert "afspraak" in out["sample_question"].lower() or "@" in out["sample_question"]
    assert "uitnodiging" in out["sample_answer"].lower() or "@" in out["sample_answer"]
    steps = out["conversation"]
    assert any(s.get("type") == "internal_calendar" for s in steps)
    customer_msgs = [s["text"] for s in steps if s.get("type") == "customer"]
    assert any("e-mail" in t.lower() or "@" in t for t in customer_msgs)
    bot_msgs = [s["text"] for s in steps if s.get("type") == "bot"]
    assert any("e-mailadres" in t.lower() for t in bot_msgs)
    assert any("uitnodiging" in t.lower() or "ontvangt" in t.lower() for t in bot_msgs)
    assert not any("vellemans" in t.lower() for t in bot_msgs)


def test_turn_to_steps_calendar_trace():
    from platform.preview_ui import turn_to_steps

    steps = turn_to_steps(
        "Kunnen we een afspraak inplannen?",
        "Ja, morgen 14:00 past.",
        industry="industrial",
        traces=[{
            "kind": "calendar",
            "provider": "Google Calendar",
            "searching": "Agenda…",
            "done": "Ingepland",
            "note": "Sync met agenda.",
        }],
    )
    assert any(s["type"] == "internal_calendar" for s in steps)


def test_run_appointment_reminder_preview():
    from platform.preview_agent import run_appointment_reminder_preview

    out = run_appointment_reminder_preview(
        _FakeAgent(),
        tenant_id="t1",
        industry="industrial",
        business_name="Vellemans",
        service_hint="de installatie (12 zonnepanelen)",
        appointment_slot="14:00",
    )
    assert out["phase"] == "reminder"
    assert any(s.get("type") == "proactive_banner" for s in out["conversation"])
    bot = next(s for s in out["conversation"] if s.get("type") == "bot")
    assert "14:00" in bot["text"]
    assert "herinnering" in bot["text"].lower()


def test_run_google_review_preview():
    from platform.preview_agent import run_google_review_preview

    out = run_google_review_preview(
        _FakeAgent(),
        tenant_id="t1",
        industry="industrial",
        business_name="Vellemans",
    )
    assert out["phase"] == "review"
    steps = out["conversation"]
    assert any(s.get("type") == "internal_review" for s in steps)
    assert steps[0]["type"] == "bot"
    assert steps[1]["type"] == "customer"
    assert "top" in steps[1]["text"].lower() or "great" in steps[1]["text"].lower()
    review_bot = [s for s in steps if s.get("type") == "bot"][-1]
    assert "review" in review_bot["text"].lower()
    assert steps[-1]["type"] == "customer"
    assert "review" in steps[-1]["text"].lower() or "goodbye" in steps[-1]["text"].lower()


def test_run_google_review_preview_includes_maps_link():
    from platform.preview_agent import run_google_review_preview

    maps_url = "https://maps.google.com/?cid=123456789"
    place_id = "ChIJtest123"
    out = run_google_review_preview(
        _FakeAgent(),
        tenant_id="t1",
        industry="industrial",
        business_name="Vellemans",
        extra={"google_maps_uri": maps_url, "place_id": place_id},
    )
    review_url = f"https://search.google.com/local/writereview?placeid={place_id}"
    steps = out["conversation"]
    review_bot = [s for s in steps if s.get("type") == "bot"][-1]
    assert review_url not in review_bot["text"]
    assert review_bot.get("review_url") == review_url
    assert review_bot.get("review_link_label")
    assert "Vellemans" in review_bot.get("review_link_detail", "")
    assert out.get("review_url") == review_url
    review_step = next(s for s in out["conversation"] if s.get("type") == "internal_review")
    assert review_url not in review_step.get("note", "")
    assert "Vellemans" in review_step.get("note", "")