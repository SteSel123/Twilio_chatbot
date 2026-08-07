"""Tests for setup knowledge preview helpers."""

from unittest.mock import patch

from platform.setup_preview import (
    _display_business_name,
    _looks_hallucinated,
    _normalize_knowledge,
    _parse_demo_json,
    _pick_fact_line,
    allowed_image,
    generate_demo_conversation,
    save_knowledge_doc,
    vision_available,
)


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


def test_generate_demo_conversation_fast():
    from platform.setup_preview import generate_demo_conversation_fast

    euro = "\u20ac"
    demo = generate_demo_conversation_fast(
        f"- Pasta carbonara — {euro}14,50\n- Caesar salade — {euro}11,00",
        "De Hoge Muur",
        "restaurant",
    )
    assert euro + "14" in demo["sample_answer"] or "carbonara" in demo["sample_question"].lower()
    assert demo["owner_summary"]


@patch("platform.setup_preview.SETUP_USE_LLM_DEMO", True)
@patch("platform.setup_preview._simple_llm")
def test_generate_demo_conversation(mock_llm):
    mock_llm.return_value = (
        '{"sample_question":"Wat kost een Caesar salade?","sample_answer":"\u20ac11 bij ons. Vers en dagvers bereid.",'
        '"fact_used":"Caesar salade — \u20ac11,00","owner_summary":"Klant vroeg prijs.",'
        '"appointment_suggestion":""}'
    )
    demo = generate_demo_conversation("- Caesar salade \u20ac11", "De Hoge Muur", "restaurant")
    assert "Caesar" in demo["sample_question"] or "salade" in demo["sample_question"].lower()


@patch("platform.setup_preview.generate_demo_conversation")
def test_process_demo_sample(mock_demo, tmp_path, monkeypatch):
    monkeypatch.setattr("platform.setup_preview.BASE_DIR", tmp_path)
    mock_demo.return_value = {
        "sample_question": "Wat kost knippen?",
        "sample_answer": "€35",
        "fact_used": "Knippen dames — €35",
        "owner_summary": "Klant vroeg naar knippen.",
        "appointment_suggestion": "Vrijdag 14:00",
        "internal_note": "📧 Samenvatting verstuurd",
    }
    from platform.setup_preview import process_demo_sample

    with patch("platform.setup_preview._attach_owner_email", side_effect=lambda r, **kw: r):
        result = process_demo_sample(
            tenant_id="demo-tenant",
            demo_id="salon-prices",
            business_name="Bella Salon",
            industry="salon",
        )
    assert result["source"] == "demo"
    assert result["demo_label"] == "Kapsalon prijslijst"


def test_list_demo_samples_by_industry():
    from platform.setup_preview import list_demo_samples

    samples = list_demo_samples("restaurant")
    assert samples[0]["id"] == "restaurant-menu"
    assert samples[0]["preview_lines"]
    assert list_demo_samples("salon")[0]["id"] == "salon-prices"
    assert len(list_demo_samples("retail")) == 1


def test_unwrap_json_knowledge():
    from platform.setup_preview import _unwrap_json_knowledge

    raw = '{"knowledge":"- Pasta €14\\n- Soep €6","sample_question":"test"}'
    assert "Pasta" in _unwrap_json_knowledge(raw)
    assert "{" not in _unwrap_json_knowledge(raw)


def test_apply_preview_ui():
    from platform.setup_preview import _apply_preview_ui, generate_demo_conversation_fast

    demo = generate_demo_conversation_fast("- Pasta — €14", "Test", "restaurant")
    out = _apply_preview_ui(
        demo,
        knowledge="- Pasta — €14",
        industry="restaurant",
        source="demo",
        demo_label="Restaurant menu",
    )
    assert out["doc_items"]
    assert out["show_web_search"] is True
    assert out["sector_question"]
    assert out["customer_thanks"]
    assert out["doc_show_lock"] is True
    assert out["show_owner_sources"] is True
    assert len(out["owner_sources"]) >= 3
    assert any(s["kind"] == "database" for s in out["owner_sources"])
    assert any(s["kind"] == "document" for s in out["owner_sources"])


def test_demo_samples_include_matching_image():
    from platform.setup_preview import list_demo_samples, get_demo_sample

    for industry in ("restaurant", "salon", "retail"):
        samples = list_demo_samples(industry)
        assert samples[0]["image_url"].startswith("demo/")
        assert samples[0]["image_caption"]
        sample = get_demo_sample(samples[0]["id"])
        assert sample
        assert "Caesar" in sample["knowledge"] or "Knippen" in sample["knowledge"] or "Openingstijden" in sample["knowledge"]


def test_apply_preview_ui_website_uses_sector_search_not_url():
    from platform.setup_preview import _apply_preview_ui, generate_demo_conversation_fast

    demo = generate_demo_conversation_fast("- Pasta — €14", "Test", "restaurant")
    out = _apply_preview_ui(
        demo,
        knowledge="- Pasta — €14",
        industry="restaurant",
        source="website",
        website_url="https://example.nl",
    )
    assert out["show_web_search"] is True
    assert "example.nl" not in out["web_query"]
    assert "weersverwachting" in out["web_query"].lower() or "terras" in out["web_query"].lower()
    assert out["customer_thanks"]


def test_process_website_preview(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.setup_preview.BASE_DIR", tmp_path)
    sample_html = """
    <html><head><title>Test Winkel</title>
    <meta name="description" content="Openingstijden en diensten">
    </head><body>
    <h1>Test Winkel</h1>
    <ul><li>Ma–Wo 10:00–18:00</li><li>Gratis maatadvies</li></ul>
    </body></html>
    """
    from platform.setup_preview import process_website_preview

    with patch("platform.setup_preview._attach_owner_email", side_effect=lambda r, **kw: r), patch(
        "platform.setup_preview.fetch_website_knowledge",
        return_value={
            "knowledge": "## Test Winkel\n- Ma–Wo 10:00–18:00\n- Gratis maatadvies",
            "og_image": "",
            "final_url": "https://example.nl/",
        },
    ):
        result = process_website_preview(
            tenant_id="web-tenant",
            business_name="Test Shop",
            industry="retail",
            website_url="https://example.nl",
        )
    assert result["source"] == "website"
    assert "10:00" in result["sample_answer"] or "10:00" in result.get("knowledge_preview", "")
    assert result["show_owner_sources"] is True
    assert "email_body" not in result


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
    ):
        result = process_business_lookup(
            tenant_id="biz-tenant",
            business_name="Test Shop",
            industry="restaurant",
            business_query="Test Utrecht",
            city="Utrecht",
            specialization="Italian restaurant",
        )
    assert result["source"] == "business"
    assert result["preview_flow"] == "business"
    assert result["show_customer_image"] is False
    assert result["show_web_search"] is False
    assert result["show_sector_web_search"] is False
    assert result["show_sector_internal"] is True
    assert result["sector_question"]
    assert "vegetarisch" in result["sector_question"].lower()
    assert result["sector_answer"]
    assert "09:00" in result["sample_answer"] or "18:00" in result["sample_answer"]
    assert "offerte" not in result["sample_answer"].lower()
    assert "welkom" in result["sample_answer"].lower()
    assert "Interne bestanden" not in result["doc_searching"]
    assert "Google" in result["doc_searching"]
    assert "09:00" in result["sample_answer"] or "18:00" in result["sample_answer"]
    assert result["sample_question"] == "Hoe laat zijn jullie vandaag open?"
    assert len(result.get("conversation", [])) >= 6
    assert result["conversation"][0]["text"] == "Hoi! 👋"


def test_process_business_lookup_no_contact_as_hours(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.setup_preview.BASE_DIR", tmp_path)
    from platform.setup_preview import process_business_lookup

    ews_knowledge = (
        "## Google — EWS Energy\n"
        "- Earth Wind & Solar Energy 0887.478.140 | Stoofstraat 39b | 1785 Merchtem | "
        "+32 52 30 60 30 | info@ewsenergy.be\n"
    )
    with patch("platform.setup_preview._attach_owner_email", side_effect=lambda r, **kw: r), patch(
        "platform.setup_preview.lookup_business_knowledge",
        return_value={
            "knowledge": ews_knowledge,
            "og_image": "",
            "website_url": "",
            "search_query": "EWS Energy",
            "business_query": "EWS Energy",
        },
    ):
        result = process_business_lookup(
            tenant_id="ews-test",
            business_name="EWS Energy",
            industry="energy",
            business_query="EWS Energy",
            city="Merchtem",
            specialization="zonnepanelen",
        )
    assert "0887.478.140" not in result["sample_answer"]
    assert "Stoofstraat" not in result["sample_answer"]
    assert "info@ewsenergy.be" not in result["sample_answer"]
    assert "afspraak" in result["sample_answer"].lower() or "vraag door" in result["sample_answer"].lower()


def test_get_default_business_lookup():
    from platform.setup_preview import get_default_business_lookup

    out = get_default_business_lookup("restaurant")
    assert out["name"]
    assert out["city"]


@patch("platform.setup_preview._generate_business_demo_llm", return_value=None)
def test_rejects_corporate_revenue_in_demo(mock_llm):
    from platform.setup_preview import generate_demo_conversation

    knowledge = (
        "## Google — Delhaize Halle\n"
        "In 2014, Delhaize Group recorded revenue of €24.5 billion in sales."
    )
    demo = generate_demo_conversation(
        knowledge,
        "Delhaize Halle",
        "retail",
        specialization="supermarket",
        source="business",
    )
    q = demo["sample_question"].lower()
    assert "recorded revenue" not in q
    assert "2014" not in demo["sample_question"]
    assert "delhaize group" not in q
    assert len(demo["sample_answer"]) >= 24
    mock_llm.assert_called_once()


def test_json_blob_not_in_demo_question():
    from platform.setup_preview import generate_demo_conversation_fast

    blob = (
        '{"knowledge":"The image shows a menu","sample_question":"What time?",'
        '"sample_answer":"8 AM","fact_used":"hours"}'
    )
    demo = generate_demo_conversation_fast(blob, "Test Restaurant", "restaurant")
    assert "{" not in demo["sample_question"]
    assert "knowledge" not in demo["sample_question"].lower()
