"""Tests for curated industry FAQ database."""

from pathlib import Path

from platform.industry_faqs import (
    list_sector_faqs,
    pick_sector_faq,
    write_industry_seed_docs,
)


def test_pick_restaurant_faq():
    faq = pick_sector_faq("restaurant", "Italian restaurant")
    assert "vegetarisch" in faq["question"].lower()
    assert faq["answer"]


def test_pick_retail_supermarket():
    faq = pick_sector_faq("retail", "supermarkt")
    assert "biologisch" in faq["question"].lower() or "bio" in faq["answer"].lower()


def test_pick_salon_faq():
    faq = pick_sector_faq("salon", "Kapsalon")
    assert "boek" in faq["question"].lower() or "van tevoren" in faq["question"].lower()


def test_pick_energy_solar():
    faq = pick_sector_faq("services", "zonnepanelen")
    assert "zonnepanel" in faq["question"].lower() or "installatie" in faq["question"].lower()
    assert "kom gerust langs" not in faq["answer"].lower()
    assert "passends voor" not in faq["question"].lower()


def test_list_sector_faqs_limit():
    items = list_sector_faqs("restaurant", "pizzeria", limit=3)
    assert 1 <= len(items) <= 3
    assert all("question" in i and "answer" in i for i in items)


def test_write_seed_docs(tmp_path):
    docs = tmp_path / "docs" / "test-shop"
    path = write_industry_seed_docs(
        docs,
        business_name="Test Shop",
        industry="restaurant",
        specialization="Italiaans restaurant",
        business_city="Utrecht",
    )
    assert path is not None
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Test Shop" in text
    assert "Veelgestelde vragen" in text
    assert write_industry_seed_docs(
        docs,
        business_name="Test Shop",
        industry="restaurant",
    ) is None
