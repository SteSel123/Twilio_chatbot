"""Tests for Kaggle FAQ merge layer."""

from platform.industry_faqs import list_sector_faqs, pick_sector_faq
from platform.kaggle_faqs import load_kaggle_faqs, merged_faq_entries


def test_load_kaggle_faqs_has_verticals():
    data = load_kaggle_faqs()
    assert "industrial" in data
    assert "logistics" in data
    assert data["industrial"][0]["question"]


def test_merged_faqs_include_kaggle():
    merged = merged_faq_entries("industrial")
    sources = {e.get("source", "") for e in merged}
    assert any("kaggle" in s for s in sources)


def test_pick_industrial_faq():
    faq = pick_sector_faq("industrial", "CNC storingsdienst")
    assert faq["industry"] == "industrial"
    assert faq["question"] and faq["answer"]


def test_list_logistics_faqs():
    items = list_sector_faqs("logistics", "transporteur", limit=4)
    assert 1 <= len(items) <= 4
