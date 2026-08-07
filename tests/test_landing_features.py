"""Tests for AppAssist landing-page feature alignment."""

from platform.analytics import get_dashboard_stats, get_monthly_conversations, record_lead, record_message
from platform.calendar import book_appointment, list_available_slots
from platform.leads import qualify_lead
from platform.outbound import list_jobs, schedule_message
from platform.tiers import check_conversation_allowed, tier_config, tier_allows_media


def test_qualify_lead_high_interest():
    result = qualify_lead("I need a haircut ASAP, ready to book today")
    assert result["interest"] == "high"
    assert result["urgency"] == "high"
    assert result["score"] >= 50


def test_qualify_lead_budget():
    result = qualify_lead("My budget is around €150 for balayage")
    assert result["budget"]


def test_tier_limits_starter():
    cfg = tier_config("default")
    assert cfg["conversations_per_month"] == 400
    assert cfg["voice_images"] is False


def test_tier_allows_media_growth():
    assert tier_allows_media("salon") is True


def test_analytics_record_and_stats():
    record_message("test-tenant", "whatsapp:+111", "inbound", intent="greeting", message_preview="hello")
    record_message("test-tenant", "whatsapp:+111", "outbound", response_ms=1200, message_preview="hi there")
    record_lead("test-tenant", "whatsapp:+111", interest="high", score=80, labels=["hot_lead"])
    stats = get_dashboard_stats("test-tenant", days=1)
    assert stats["inbound_messages"] >= 1
    assert stats["leads_count"] >= 1


def test_conversation_limit_check():
    allowed, _ = check_conversation_allowed("salon")
    assert allowed is True


def test_calendar_slots():
    slots = list_available_slots("salon", "2026-12-01")
    assert len(slots) > 0
    assert "09:00" in slots


def test_book_appointment():
    result = book_appointment(
        "salon",
        "whatsapp:+32470000000",
        date="2026-12-01",
        slot_time="10:00",
        service="Haircut",
    )
    assert result["ok"] is True
    assert "calendar_link" in result


def test_outbound_schedule():
    job_id = schedule_message(
        "salon",
        "whatsapp:+32470000000",
        "custom",
        "Test reminder",
    )
    assert job_id > 0
    jobs = list_jobs("salon", limit=5)
    assert any(j["id"] == job_id for j in jobs)


def test_mcp_registry_new_tools():
    from platform.mcp import ToolRegistry

    reg = ToolRegistry(tenant_id="salon")
    result = reg.invoke("qualifyLead", {"message": "Need quote urgently"}, tenant_id="salon")
    assert "interest" in result
