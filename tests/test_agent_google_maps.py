"""Agent integration — Google Maps context for live WhatsApp."""

from unittest.mock import patch

from platform.business_profile import BusinessProfile


@patch("agent.openai_tool_calling_available", return_value=False)
@patch("agent.generate_response", return_value="Vandaag open tot 17:00.")
@patch(
    "agent.get_maps_context_for_profile",
    return_value=(
        "## Google Maps (bron van waarheid voor openingstijden, adres en locatie-link)\n"
        "- **Adres:** Stoofstraat 39b, Merchtem\n"
        "- **Google Maps URL:** https://maps.google.com/?cid=123"
    ),
)
@patch("agent.vector_search", return_value="")
def test_agent_injects_google_maps_for_hours(mock_rag, mock_maps, mock_llm, mock_tooling):
    from agent import BusinessAgent

    agent = BusinessAgent()
    uid = "whatsapp:+32470000001"
    tenant = "maps-test"

    profile = BusinessProfile(
        tenant_id=tenant,
        business_name="EWS Energy",
        business_city="Merchtem",
        industry="construction",
    )
    with patch("agent.load_business_profile", return_value=profile):
        agent.handle_message(uid, "yes", tenant_id=tenant)
        agent.handle_message(uid, "Hoe laat zijn jullie vandaag open?", tenant_id=tenant)

    mock_maps.assert_called()
    internal = mock_llm.call_args.kwargs["internal_context"]
    assert "Google Maps URL" in internal
    assert "Stoofstraat" in internal


@patch("agent.openai_tool_calling_available", return_value=False)
@patch("agent.generate_response", return_value="Adres: Stationsstraat 1")
@patch("agent.get_maps_context_for_profile", return_value="")
@patch("agent.vector_search", return_value="")
def test_agent_skips_maps_for_unrelated_question(mock_rag, mock_maps, mock_llm, mock_tooling):
    from agent import BusinessAgent

    agent = BusinessAgent()
    uid = "whatsapp:+32470000002"
    tenant = "maps-test-2"

    profile = BusinessProfile(
        tenant_id=tenant,
        business_name="EWS Energy",
        business_city="Merchtem",
        industry="construction",
    )
    with patch("agent.load_business_profile", return_value=profile):
        agent.handle_message(uid, "yes", tenant_id=tenant)
        agent.handle_message(uid, "Wat kost een warmtepomp?", tenant_id=tenant)

    mock_maps.assert_not_called()
