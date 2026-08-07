"""Tests for owner e-mail notifications."""

from unittest.mock import patch

from platform.owner_email import _format_email_body, send_owner_summary


def test_format_email_body_with_appointment():
    body = _format_email_body(
        business_name="Salon X",
        question="Wat kost knippen?",
        answer="€35",
        summary="Warme lead — follow-up aanbevolen.",
        appointment="Vrijdag 14:00 — knippen",
    )
    assert "Salon X" in body
    assert "Vrijdag 14:00" in body
    assert "Warme lead" in body


@patch("platform.owner_email.smtp_configured", return_value=False)
def test_send_owner_summary_outbox(mock_smtp, tmp_path, monkeypatch):
    monkeypatch.setattr("platform.owner_email.OUTBOX_DIR", tmp_path)
    result = send_owner_summary(
        to_email="owner@example.com",
        business_name="Test BV",
        question="Hallo?",
        answer="Hi!",
        summary="Test samenvatting",
    )
    assert result["email_to"] == "owner@example.com"
    assert result["email_body"]
    assert not result["email_sent"]
    assert list(tmp_path.glob("*.txt"))
