"""Shared SMB tool implementations — used by WhatsApp agent and MCP server."""

from __future__ import annotations

import json
from typing import Any

from config import DEFAULT_TENANT_ID
from doc_loader import format_doc_context, load_all_docs, search_docs
from platform.business_profile import load_business_profile
from platform.rate_limit import allow_tool
from rag.vector_store import vector_search
from search import format_search_context, web_search
from storage import get_data_store
from user_data import _storage_key


def search_business_docs(query: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    profile = load_business_profile(tenant_id)
    documents = load_all_docs(profile.docs_dir)
    result = vector_search(query, documents, tenant_id=tenant_id)
    if result:
        return result
    hits = search_docs(query, documents)
    return format_doc_context(hits) or "No internal docs matched."


def get_customer_context(user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    store = get_data_store()
    scoped = _storage_key(user_id, tenant_id)
    state = store.get_case_state(scoped)
    personal = store.get_personal_data(scoped)
    return json.dumps({"context": state, "customer_data": personal}, default=str)


def web_search_for_tenant(query: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    profile = load_business_profile(tenant_id)
    enriched = f"{profile.business_name} {profile.industry} {query}"
    results = web_search(enriched)
    return format_search_context(results) or "No web results."


def execute_tool(
    tool_name: str,
    args: dict[str, Any],
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = "",
    correlation_id: str = "",
) -> str:
    """Run a core or external tool. Single entry point for agent + MCP."""
    from platform.mcp import ToolRegistry

    aliases = {
        "searchImmigrationDocs": "searchBusinessDocs",
        "getUserCaseStatus": "getCustomerContext",
        "search_business_docs": "searchBusinessDocs",
        "get_customer_context": "getCustomerContext",
        "web_search": "webSearch",
    }
    normalized = aliases.get(tool_name, tool_name)

    if normalized == "callExternalTool":
        from platform.mcp_external import call_external_tool

        return call_external_tool(
            tenant_id=tenant_id,
            server_label=args.get("server_label", args.get("label", "")),
            tool_name=args.get("tool_name", ""),
            arguments=args.get("arguments") or {},
            user_id=user_id or args.get("user_id", ""),
        )

    if normalized == "listExternalIntegrations":
        from platform.mcp_external import list_external_integrations

        return list_external_integrations(tenant_id)

    registry = ToolRegistry(get_data_store(), tenant_id=tenant_id)
    return registry.invoke(
        normalized,
        args,
        tenant_id=tenant_id,
        user_id=user_id,
        correlation_id=correlation_id,
    )
