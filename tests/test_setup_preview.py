"""Tests for setup knowledge preview helpers."""

from unittest.mock import MagicMock, patch

from platform.setup_preview import (
    _display_business_name,
    _looks_hallucinated,
    _normalize_knowledge,
    _parse_demo_json,
    _pick_fact_line,
    allowed_image,
    render_demo_site_html,
    save_knowledge_doc,
    vision_available,
)


def _mock_agent():
    agent = MagicMock()
    agent.reload_docs = MagicMock()
    return agent


def _agentic_preview_payload(*, await_upload=False, append=False, phase="opening_hours"):
    conv = [
        {"type": "customer", "text": "Hoe laat zijn jullie vandaag open?"},
        {"type": "internal_docs", "doc_files": ["Google Maps"]},
        {"type": "bot", "text": "Vandaag open tot 18:00 uur."},
    ]
    if phase == "upload":
        conv = [
            {"type": "customer", "text": "Hoi! CNC lijn 2 foutcode E47 — storingsdienst vandaag?"},
            {"type": "internal_docs", "doc_files": ["Geüpload document"]},
            {"type": "bot", "text": "Storingsdienst kan vandaag tussen 13:00–17:00."},
        ]
    return {
        "conversation": conv,
        "preview_mode": "agentic",
        "phase": phase,
        "await_upload": await_upload,
        "append": append,
        "progress_label": "Google → openingstijden → antwoord",
        "doc_files": ["Onderhoudstarieven.pdf"],
        "progress_steps": 5,
        "sample_question": conv[0]["text"],
        "sample_answer": conv[-1]["text"],
    }


def test_allowed_image():
    assert allowed_image("menu.jpg", "image/jpeg")
    assert allowed_image("doc.pdf", "application/pdf")


def test_normalize_knowledge():
    assert _normalize_knowledge("```\nMenu\n```") == "Menu"


def test_hallucination_detection():
    assert _looks_hallucinated("Contact: info@example.com")
    assert not _looks_hallucinated("Kapsel €35")


def test_display_business_name_from_filename():
    assert _display_business_name("test3", "re49-menu-De-Hoge-Muur.jpg") == "De Hoge Muur"
    assert _display_business_name("Bella Salon", "menu.jpg") == "Bella Salon"


def test_pick_fact_line():
    knowledge = "Menu\n- Burger €12\nOpeningstijden ma-vr 9-17"
    assert "€12" in (_pick_fact_line(knowledge) or "")


def test_parse_demo_json():
    raw = '{"sample_question":"Wat kost de burger?","sample_answer":"€12","fact_used":"Burger €12"}'
    data = _parse_demo_json(raw)
    assert data and data["sample_question"] == "Wat kost de burger?"


def test_save_knowledge_doc(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.setup_preview.BASE_DIR", tmp_path)
    dest = save_knowledge_doc("salon-x", "Prijs knippen: €35", "menu.jpg")
    assert "€35" in dest.read_text(encoding="utf-8")


def test_render_demo_site_html_uses_verticals():
    html = render_demo_site_html("industrial")
    assert "Storingsdienst" in html
    assert "industrie" in html.lower() or "Onderhoudstarieven" in html


def test_unwrap_json_knowledge():
    from platform.setup_preview import _unwrap_json_knowledge

    raw = '{"knowledge":"- Pasta €14\\n- Soep €6","sample_question":"test"}'
    assert "Pasta" in _unwrap_json_knowledge(raw)
    assert "{" not in _unwrap_json_knowledge(raw)


def test_fetch_website_knowledge_extracts_html():
    from platform.setup_preview import _html_to_knowledge

    html = "<html><head><title>Cafe</title></head><body><h2>Menu</h2><ul><li>Soep €6</li></ul></body></html>"
    knowledge = _html_to_knowledge(html)
    assert "Cafe" in knowledge
    assert "Soep" in knowledge


def test_process_business_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.setup_preview.BASE_DIR", tmp_path)
    from platform.setup_preview import process_business_lookup

    with patch("platform.setup_preview._attach_owner_email", side_effect=lambda r, **kw: r), patch(
        "platform.setup_preview.lookup_business_knowledge",
        return_value={
            "knowledge": "## Google Maps — Openingstijden\n- **Vandaag:** Vandaag zijn we open: 09:00–18:00 uur.",
            "og_image": "",
            "website_url": "",
            "search_query": "Test Utrecht",
            "business_query": "Test Utrecht",
            "google_maps_hours": True,
            "opening_hours_today": "Vandaag zijn we open: 09:00–18:00 uur.",
        },
    ), patch(
        "platform.preview_agent.run_opening_hours_preview",
        return_value=_agentic_preview_payload(await_upload=True),
    ):
        result = process_business_lookup(
            tenant_id="biz-tenant",
            business_name="Test Shop",
            industry="industrial",
            business_query="Test Utrecht",
            city="Utrecht",
            specialization="CNC onderhoud",
            agent=_mock_agent(),
        )
    assert result["source"] == "business"
    assert result["preview_mode"] == "agentic"
    assert result["await_upload"] is True
    assert "open" in result["sample_question"].lower() or "hoe laat" in result["sample_question"].lower()
    assert len(result.get("conversation", [])) >= 3


def test_process_business_lookup_no_contact_as_hours(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.setup_preview.BASE_DIR", tmp_path)
    from platform.setup_preview import process_business_lookup

    ews_knowledge = (
        "## Google — EWS Energy\n"
        "- Earth Wind & Solar Energy 0887.478.140 | Stoofstraat 39b | 1785 Merchtem | "
        "+32 52 30 60 30 | info@ewsenergy.be\n"
    )
    payload = _agentic_preview_payload(await_upload=True)
    payload["conversation"][2]["text"] = "We plannen graag een technische intake op locatie."
    with patch("platform.setup_preview._attach_owner_email", side_effect=lambda r, **kw: r), patch(
        "platform.setup_preview.lookup_business_knowledge",
        return_value={
            "knowledge": ews_knowledge,
            "og_image": "",
            "website_url": "",
            "search_query": "EWS Energy",
            "business_query": "EWS Energy",
        },
    ), patch(
        "platform.preview_agent.run_opening_hours_preview",
        return_value=payload,
    ):
        result = process_business_lookup(
            tenant_id="ews-test",
            business_name="EWS Energy",
            industry="construction",
            business_query="EWS Energy",
            city="Merchtem",
            specialization="warmtepomp installatie",
            agent=_mock_agent(),
        )
    assert "0887.478.140" not in result["sample_answer"]
    assert "Stoofstraat" not in result["sample_answer"]
    assert "info@ewsenergy.be" not in result["sample_answer"]


def test_get_default_business_lookup():
    from platform.setup_preview import get_default_business_lookup

    out = get_default_business_lookup("industrial")
    assert out["name"]
    assert out["city"]


def test_build_upload_customer_question_from_solar_doc():
    from platform.setup_preview import build_upload_customer_question

    knowledge = (
        "12 zonnepanelen (2550 kWh/jaar) | materiaal: € 2.600 – € 3.000 | "
        "installatie: € 950 tot € 1.100 | totaal: € 3.550 tot € 4.100"
    )
    q = build_upload_customer_question(
        knowledge, "Vellemans", "industrial", source_name="zonnepanelen.png", locale="nl"
    )
    assert "zonnepanelen" in q.lower()
    assert "cnc" not in q.lower()
    assert "e47" not in q.lower()

    q_en = build_upload_customer_question(
        knowledge, "Vellemans", "industrial", source_name="zonnepanelen.png", locale="en"
    )
    assert "solar panels" in q_en.lower()
    assert "zonnepanelen" not in q_en.lower()


def test_build_upload_customer_question_from_filename_when_no_prices():
    from platform.setup_preview import build_upload_customer_question

    q = build_upload_customer_question("", "Vellemans", "industrial", source_name="zonnepanelen.png", locale="nl")
    assert "zonnepanelen" in q.lower()
    assert "cnc" not in q.lower()

    q_en = build_upload_customer_question("", "Vellemans", "industrial", source_name="zonnepanelen.png", locale="en")
    assert "solar panels" in q_en.lower()
