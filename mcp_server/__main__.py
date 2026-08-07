"""MCP server — stdio (Cursor), Streamable HTTP + SSE (OpenAI Remote MCP, web copilot)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Project root on path before local `platform/` package
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import DEFAULT_TENANT_ID, MCP_API_KEY, MCP_HOST, MCP_PORT
from mcp.server.mcpserver import MCPServer
from platform.mcp_tools import (
    execute_tool,
    get_customer_context,
    search_business_docs,
    web_search_for_tenant,
)

mcp = MCPServer(
    "smb-whatsapp-tools",
    instructions=(
        "SMB WhatsApp assistant tools. Pass tenant_id on every call (e.g. 'salon', 'restaurant'). "
        "Use list_external_integrations and call_external_tool for CRM/booking/inventory MCP plugins."
    ),
)


def _resolve_tenant(tenant_id: str | None) -> str:
    return tenant_id or os.getenv("DEFAULT_TENANT_ID", DEFAULT_TENANT_ID)


@mcp.tool(name="search_business_docs")
def search_business_docs_tool(query: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    """Search the business knowledge base (hours, prices, services, policies)."""
    return search_business_docs(query, _resolve_tenant(tenant_id))


@mcp.tool(name="get_customer_context")
def get_customer_context_tool(
    user_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> str:
    """Return stored customer context (topic, service type, provided items, personal fields)."""
    return get_customer_context(user_id, _resolve_tenant(tenant_id))


@mcp.tool(name="web_search")
def web_search_tool(query: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    """Search the web with business name/industry context for fresh public information."""
    return web_search_for_tenant(query, _resolve_tenant(tenant_id))


@mcp.tool(name="list_external_integrations")
def list_external_integrations_tool(tenant_id: str = DEFAULT_TENANT_ID) -> str:
    """List external MCP integrations configured for this business (CRM, booking, inventory)."""
    return execute_tool("listExternalIntegrations", {}, tenant_id=_resolve_tenant(tenant_id))


@mcp.tool(name="call_external_tool")
def call_external_tool_tool(
    server_label: str,
    tool_name: str,
    arguments: dict,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = "",
) -> str:
    """Invoke a tool on an external MCP server registered for this tenant."""
    return execute_tool(
        "callExternalTool",
        {
            "server_label": server_label,
            "tool_name": tool_name,
            "arguments": arguments,
            "user_id": user_id,
        },
        tenant_id=_resolve_tenant(tenant_id),
        user_id=user_id,
    )


@mcp.tool(name="qualify_lead")
def qualify_lead_tool(message: str, tenant_id: str = DEFAULT_TENANT_ID, user_id: str = "") -> str:
    """Score lead interest, budget, and urgency from a customer message."""
    return execute_tool(
        "qualifyLead",
        {"message": message, "user_id": user_id},
        tenant_id=_resolve_tenant(tenant_id),
        user_id=user_id,
    )


@mcp.tool(name="book_appointment")
def book_appointment_tool(
    date: str,
    time: str,
    service: str = "",
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = "",
) -> str:
    """Book an appointment and sync to Google Calendar when configured."""
    return execute_tool(
        "bookAppointment",
        {"date": date, "time": time, "service": service, "user_id": user_id},
        tenant_id=_resolve_tenant(tenant_id),
        user_id=user_id,
    )


@mcp.tool(name="list_available_slots")
def list_slots_tool(date: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    """List available appointment slots for a date (YYYY-MM-DD)."""
    return execute_tool(
        "listAvailableSlots",
        {"date": date},
        tenant_id=_resolve_tenant(tenant_id),
    )


@mcp.tool(name="create_payment_link")
def payment_link_tool(
    amount_cents: int,
    description: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = "",
) -> str:
    """Create a Stripe payment link for proactive WhatsApp payments."""
    return execute_tool(
        "createPaymentLink",
        {"amount_cents": amount_cents, "description": description, "user_id": user_id},
        tenant_id=_resolve_tenant(tenant_id),
        user_id=user_id,
    )


@mcp.tool(name="schedule_reminder")
def schedule_reminder_tool(
    user_id: str,
    appointment_time: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    hours_before: float = 24,
) -> str:
    """Schedule a proactive appointment reminder via WhatsApp."""
    return execute_tool(
        "scheduleReminder",
        {"user_id": user_id, "appointment_time": appointment_time, "hours_before": hours_before},
        tenant_id=_resolve_tenant(tenant_id),
        user_id=user_id,
    )


def _configure_auth() -> None:
    """Optional Bearer token auth for HTTP/SSE (OpenAI Remote MCP, production)."""
    if not MCP_API_KEY:
        return

    from mcp.server.auth.provider import AccessToken, TokenVerifier

    class StaticMcpApiKeyVerifier:
        async def verify_token(self, token: str) -> AccessToken | None:
            if token == MCP_API_KEY:
                return AccessToken(token=token, client_id="mcp-client", scopes=["mcp:tools"])
            return None

    mcp._token_verifier = StaticMcpApiKeyVerifier()  # type: ignore[attr-defined]
    from mcp.server.auth.settings import AuthSettings

    mcp.settings.auth = AuthSettings(
        issuer_url=os.getenv("MCP_ISSUER_URL", "https://localhost"),
        resource_server_url=os.getenv("MCP_RESOURCE_URL", f"http://{MCP_HOST}:{MCP_PORT}"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SMB WhatsApp MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=MCP_HOST)
    parser.add_argument("--port", type=int, default=MCP_PORT)
    args = parser.parse_args()

    if args.transport != "stdio":
        _configure_auth()

    kwargs = {"host": args.host, "port": args.port}
    if args.transport == "streamable-http":
        kwargs["stateless_http"] = True
        kwargs["json_response"] = True

    mcp.run(transport=args.transport, **kwargs)


if __name__ == "__main__":
    main()
