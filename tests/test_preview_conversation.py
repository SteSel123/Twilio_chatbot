"""Tests for multi-turn preview conversations."""

from platform.preview_conversation import (
    attach_preview_conversation,
    build_business_conversation,
    build_upload_conversation,
)


def test_business_conversation_has_multiple_turns():
    result = {
        "sample_question": "Hoe laat zijn jullie vandaag open?",
        "sample_answer": "Vandaag open tot 22:00.",
        "sector_question": "Super, dank je! Hebben jullie vegetarische gerechten?",
        "sector_answer": "Ja, meerdere vegetarische opties.",
        "doc_files": ["menu.pdf"],
        "sector_doc_files": ["branche-info.md"],
        "sector_found_message": "Antwoord gevonden in branchebestanden",
        "response_tags": ["Info uit bron"],
    }
    steps = build_business_conversation(result, industry="restaurant")
    types = [s["type"] for s in steps]
    assert types.count("customer") >= 3
    assert types.count("bot") >= 2
    assert "Hoi! 👋" in steps[0]["text"]
    assert "Ah top, dank je wel!" in steps[4]["text"]
    assert steps[-2]["type"] == "customer"
    assert "langskom" in steps[-2]["text"].lower() or "kom" in steps[-2]["text"].lower()
    assert "nee, dat was het" not in steps[-2]["text"].lower()
    assert steps[-1]["type"] == "bot"
    assert "tot" in steps[-1]["text"].lower() or "graag" in steps[-1]["text"].lower()
    assert not any(
        s.get("text") == "Kan ik nog iets anders voor je regelen?" for s in steps if s["type"] == "bot"
    )


def test_upload_conversation_follow_up():
    result = {
        "sample_question": "Wat kost pasta carbonara?",
        "sample_answer": "Pasta carbonara kost €14,50.",
        "doc_found_message": "Antwoord gevonden in je geüpload document.",
        "response_tags": ["Prijs bevestigd"],
    }
    steps = build_upload_conversation(result, industry="restaurant", business_name="De Hoge Muur")
    assert steps[0]["type"] == "customer"
    assert steps[1]["type"] == "internal_note"
    assert "geüpload document" in steps[1]["text"].lower()
    assert not any(s["type"] == "internal_docs" for s in steps)
    assert any(s["type"] == "customer" and "reserveren" in s["text"].lower() for s in steps)
    assert steps[-1]["type"] == "bot"
    assert "tot vanavond" in steps[-1]["text"].lower() or "graag" in steps[-1]["text"].lower()


def test_attach_preview_conversation_sets_progress():
    result = attach_preview_conversation(
        {
            "preview_flow": "business",
            "sample_question": "Hoe laat zijn jullie open?",
            "sample_answer": "Tot 18:00.",
            "sector_question": "",
            "sector_answer": "",
            "doc_files": [],
        },
        source="business",
        industry="retail",
    )
    assert len(result["conversation"]) >= 4
    assert result["progress_steps"] == len(result["conversation"])
    assert "WhatsApp-gesprek" in result["progress_label"]
