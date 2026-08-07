"""Connect to external MCP servers configured per business (CRM, booking, inventory)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from platform.business_profile import load_business_profile

logger = logging.getLogger(__name__)


def list_external_integrations(tenant_id: str) -> str:
    profile = load_business_profile(tenant_id)
    servers = getattr(profile, "external_mcp_servers", None) or []
    summary = []
    for s in servers:
        summary.append(
            {
                "label": s.get("label"),
                "url": s.get("url"),
                "transport": s.get("transport", "streamable-http"),
                "description": s.get("description", ""),
            }
        )
    return json.dumps({"tenant_id": tenant_id, "integrations": summary}, indent=2)


def _auth_headers(server_cfg: dict) -> dict[str, str]:
    headers: dict[str, str] = {}
    token_env = server_cfg.get("bearer_token_env") or server_cfg.get("auth_token_env")
    if token_env:
        token = os.getenv(token_env, "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    static = server_cfg.get("bearer_token", "")
    if static:
        headers["Authorization"] = f"Bearer {static}"
    return headers


async def _call_streamable_http(url: str, tool_name: str, arguments: dict, headers: dict) -> str:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url, headers=headers or None) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
            return "\n".join(parts) or json.dumps(result.model_dump(), default=str)


def call_external_tool(
    tenant_id: str,
    server_label: str,
    tool_name: str,
    arguments: dict[str, Any],
    user_id: str = "",
) -> str:
    """Synchronously invoke a tool on a tenant's external MCP server."""
    profile = load_business_profile(tenant_id)
    servers = getattr(profile, "external_mcp_servers", None) or []
    cfg = next((s for s in servers if s.get("label") == server_label), None)
    if not cfg:
        return f"No external MCP server with label '{server_label}' for tenant '{tenant_id}'."

    url = cfg.get("url", "").rstrip("/")
    if not url.endswith("/mcp"):
        url = f"{url}/mcp" if "/mcp" not in url else url

    headers = _auth_headers(cfg)
    if user_id:
        headers["X-User-Id"] = user_id
    headers["X-Tenant-Id"] = tenant_id

    transport = cfg.get("transport", "streamable-http")
    try:
        import anyio

        if transport in ("streamable-http", "http"):
            return anyio.run(_call_streamable_http, url, tool_name, arguments, headers)
        return f"Unsupported external transport: {transport}. Use streamable-http."
    except Exception as exc:
        logger.exception("External MCP call failed: %s/%s", server_label, tool_name)
        return f"External MCP error: {exc}"


async def discover_external_tools(tenant_id: str, server_label: str) -> list[dict]:
    """List tools available on an external MCP server."""
    profile = load_business_profile(tenant_id)
    servers = getattr(profile, "external_mcp_servers", None) or []
    cfg = next((s for s in servers if s.get("label") == server_label), None)
    if not cfg:
        return []

    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    url = cfg.get("url", "").rstrip("/")
    if not url.endswith("/mcp"):
        url = f"{url}/mcp"

    headers = _auth_headers(cfg)
    async with streamable_http_client(url, headers=headers or None) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return [{"name": t.name, "description": t.description or ""} for t in tools.tools]
