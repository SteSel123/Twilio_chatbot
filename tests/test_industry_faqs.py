"""Tests for curated industry FAQ database."""

from pathlib import Path

from platform.industry_faqs import (
    list_sector_faqs,
    pick_sector_faq,
    write_industry_seed_docs,
)


def test_pick_industrial_faq():
    faq = pick_sector_faq("industrial", "CNC storingsdienst")
    assert "storing" in faq["question"].lower() or "onderhoud" in faq["question"].lower()
    assert faq["industry"] == "industrial"
    assert faq["answer"]


def test_pick_construction_faq():
    faq = pick_sector_faq("construction", "warmtepomp installateur")
    assert faq["industry"] == "construction"
    assert "intake" in faq["question"].lower() or "warmtepomp" in faq["question"].lower() or "offerte" in faq["question"].lower()


def test_pick_logistics_faq():
    faq = pick_sector_faq("logistics", "transporteur")
    assert "zending" in faq["question"].lower() or "track" in faq["question"].lower() or "lever" in faq["question"].lower()


def test_pick_construction_from_specialization():
    faq = pick_sector_faq("construction", "warmtepomp installatie")
    assert faq["industry"] == "construction"


def test_list_sector_faqs_limit():
    items = list_sector_faqs("financial", "verzekering", limit=3)
    assert 1 <= len(items) <= 3
    assert all("question" in i and "answer" in i for i in items)


def test_write_seed_docs(tmp_path):
    docs = tmp_path / "docs" / "test-shop"
    path = write_industry_seed_docs(
        docs,
        business_name="TechServ Industrial",
        industry="industrial",
        specialization="CNC onderhoud",
        business_city="Rotterdam",
    )
    assert path is not None
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "TechServ Industrial" in text
    assert "Veelgestelde vragen" in text
    assert write_industry_seed_docs(
        docs,
        business_name="TechServ Industrial",
        industry="industrial",
    ) is None
