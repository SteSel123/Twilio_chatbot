"""MCP shared tools tests."""

from platform.mcp_tools import get_customer_context, search_business_docs, web_search_for_tenant


def test_search_business_docs_default():
    result = search_business_docs("hours", "default")
    assert isinstance(result, str)
    assert result  # default docs exist


def test_get_customer_context_empty():
    result = get_customer_context("whatsapp:+99999999", "default")
    assert "context" in result


def test_list_external_integrations_empty():
    from platform.mcp_external import list_external_integrations

    data = list_external_integrations("default")
    assert "integrations" in data
