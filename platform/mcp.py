"""MCP tool registry — generic SMB tools."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from config import BASE_DIR, DEFAULT_TENANT_ID
from doc_loader import format_doc_context, load_all_docs, search_docs
from platform.auth import authorize
from platform.business_profile import load_business_profile
from platform.observability import log_structured, redact_pii
from platform.rate_limit import allow_tool
from search import format_search_context, web_search
from user_data import UserDataStore, _storage_key

AUDIT_DB = BASE_DIR / ".user_data" / "audit.db"

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "searchBusinessDocs": {
        "description": "Search internal business knowledge base",
        "parameters": {"query": "string", "tenant_id": "string"},
    },
    "getCustomerContext": {
        "description": "Return stored customer context for the user",
        "parameters": {"user_id": "string", "tenant_id": "string"},
    },
    "webSearch": {
        "description": "Search the web for business-relevant information",
        "parameters": {"query": "string"},
    },
    "listExternalIntegrations": {
        "description": "List external MCP integrations (CRM, booking, inventory)",
        "parameters": {"tenant_id": "string"},
    },
    "callExternalTool": {
        "description": "Invoke a tool on an external MCP server",
        "parameters": {"server_label": "string", "tool_name": "string", "arguments": "object"},
    },
    "qualifyLead": {
        "description": "Score lead interest, budget, and urgency",
        "parameters": {"message": "string", "user_id": "string"},
    },
    "bookAppointment": {
        "description": "Book an appointment and sync to calendar",
        "parameters": {"date": "string", "time": "string", "service": "string", "user_id": "string"},
    },
    "listAvailableSlots": {
        "description": "List available appointment slots for a date",
        "parameters": {"date": "string"},
    },
    "createPaymentLink": {
        "description": "Create a Stripe payment link for the customer",
        "parameters": {"amount_cents": "integer", "description": "string", "user_id": "string"},
    },
    "scheduleReminder": {
        "description": "Schedule a proactive appointment reminder",
        "parameters": {"user_id": "string", "appointment_time": "string", "hours_before": "number"},
    },
    # Legacy aliases
    "searchImmigrationDocs": {
        "description": "Alias for searchBusinessDocs",
        "parameters": {"query": "string"},
    },
    "getUserCaseStatus": {
        "description": "Alias for getCustomerContext",
        "parameters": {"user_id": "string", "tenant_id": "string"},
    },
}

DEFAULT_TOOLS = {
    "searchBusinessDocs",
    "getCustomerContext",
    "webSearch",
    "listExternalIntegrations",
    "callExternalTool",
    "qualifyLead",
    "bookAppointment",
    "listAvailableSlots",
    "createPaymentLink",
    "scheduleReminder",
}


def _init_audit_db() -> None:
    AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(AUDIT_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                tenant_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                user_id TEXT,
                args_json TEXT,
                result_summary TEXT,
                correlation_id TEXT
            )
            """
        )


def audit_tool_call(
    tenant_id: str,
    tool_name: str,
    user_id: str,
    args: dict[str, Any],
    result_summary: str,
    correlation_id: str = "",
) -> None:
    _init_audit_db()
    with sqlite3.connect(AUDIT_DB) as conn:
        conn.execute(
            """
            INSERT INTO tool_audit (ts, tenant_id, tool_name, user_id, args_json, result_summary, correlation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                tenant_id,
                tool_name,
                user_id,
                json.dumps({k: redact_pii(str(v)) for k, v in args.items()}),
                redact_pii(result_summary[:500]),
                correlation_id,
            ),
        )
    log_structured("tool_audit", tool=tool_name, tenant_id=tenant_id, user_id=user_id)


class ToolRegistry:
    def __init__(self, data_store: UserDataStore | None = None, tenant_id: str = DEFAULT_TENANT_ID):
        self.data_store = data_store or UserDataStore()
        self.tenant_id = tenant_id
        self._documents: dict[str, str] = {}
        self.reload_docs(tenant_id)
        _init_audit_db()

    def reload_docs(self, tenant_id: str | None = None) -> None:
        tid = tenant_id or self.tenant_id
        profile = load_business_profile(tid)
        self._documents = load_all_docs(profile.docs_dir)

    def allowed_tools(self, tenant_id: str) -> set[str]:
        profile = load_business_profile(tenant_id)
        return set(profile.enabled_tools) | DEFAULT_TOOLS

    def is_allowed(self, tenant_id: str, tool_name: str) -> bool:
        aliases = {
            "searchImmigrationDocs": "searchBusinessDocs",
            "getUserCaseStatus": "getCustomerContext",
        }
        normalized = aliases.get(tool_name, tool_name)
        return normalized in self.allowed_tools(tenant_id)

    def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        tenant_id: str = DEFAULT_TENANT_ID,
        user_id: str = "",
        correlation_id: str = "",
    ) -> str:
        aliases = {
            "searchImmigrationDocs": "searchBusinessDocs",
            "getUserCaseStatus": "getCustomerContext",
        }
        tool_name = aliases.get(tool_name, tool_name)

        if not authorize("tool", tool_name):
            return "Tool access denied by policy."
        if not self.is_allowed(tenant_id, tool_name):
            return f"Tool {tool_name} not enabled for this business."
        if not allow_tool(tenant_id, tool_name):
            return "Tool rate limit exceeded."

        if tenant_id != self.tenant_id:
            self.reload_docs(tenant_id)

        handlers: dict[str, Callable[..., str]] = {
            "searchBusinessDocs": self._search_docs,
            "getCustomerContext": self._customer_context,
            "webSearch": self._web_search,
            "listExternalIntegrations": self._list_external,
            "callExternalTool": self._call_external,
            "qualifyLead": self._qualify_lead,
            "bookAppointment": self._book_appointment,
            "listAvailableSlots": self._list_slots,
            "createPaymentLink": self._payment_link,
            "scheduleReminder": self._schedule_reminder,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return f"Unknown tool: {tool_name}"

        result = handler(args, tenant_id=tenant_id, user_id=user_id)
        audit_tool_call(tenant_id, tool_name, user_id, args, result, correlation_id)
        return result

    def _search_docs(self, args: dict[str, Any], tenant_id: str = DEFAULT_TENANT_ID, **_: Any) -> str:
        from platform.mcp_tools import search_business_docs

        tid = args.get("tenant_id") or tenant_id
        return search_business_docs(args.get("query", ""), tid)

    def _customer_context(self, args: dict[str, Any], tenant_id: str, user_id: str, **_: Any) -> str:
        from platform.mcp_tools import get_customer_context

        uid = args.get("user_id") or user_id
        return get_customer_context(uid, args.get("tenant_id") or tenant_id)

    def _web_search(self, args: dict[str, Any], tenant_id: str = DEFAULT_TENANT_ID, **_: Any) -> str:
        from platform.mcp_tools import web_search_for_tenant
        from platform.tiers import tier_allows_web_search

        if not tier_allows_web_search(tenant_id):
            return "Web search is not available on the current plan."
        tid = args.get("tenant_id") or tenant_id
        return web_search_for_tenant(args.get("query", ""), tid)

    def _list_external(self, args: dict[str, Any], tenant_id: str = DEFAULT_TENANT_ID, **_: Any) -> str:
        from platform.mcp_external import list_external_integrations

        return list_external_integrations(args.get("tenant_id") or tenant_id)

    def _call_external(self, args: dict[str, Any], tenant_id: str, user_id: str, **_: Any) -> str:
        from platform.mcp_external import call_external_tool

        return call_external_tool(
            tenant_id=tenant_id,
            server_label=args.get("server_label", args.get("label", "")),
            tool_name=args.get("tool_name", ""),
            arguments=args.get("arguments") or {},
            user_id=user_id or args.get("user_id", ""),
        )

    def _qualify_lead(self, args: dict[str, Any], tenant_id: str, user_id: str, **_: Any) -> str:
        from platform.analytics import record_lead
        from platform.leads import qualify_lead

        message = args.get("message", "")
        result = qualify_lead(message)
        uid = args.get("user_id") or user_id
        record_lead(
            tenant_id,
            uid,
            interest=result["interest"],
            budget=result["budget"],
            urgency=result["urgency"],
            score=result["score"],
            labels=result["labels"],
        )
        return json.dumps(result)

    def _book_appointment(self, args: dict[str, Any], tenant_id: str, user_id: str, **_: Any) -> str:
        from platform.calendar import book_appointment
        from platform.outbound import schedule_appointment_reminder

        profile = load_business_profile(tenant_id)
        uid = args.get("user_id") or user_id
        result = book_appointment(
            tenant_id,
            uid,
            date=args.get("date", ""),
            slot_time=args.get("time", ""),
            service=args.get("service", ""),
            customer_name=args.get("customer_name", ""),
        )
        if result.get("ok"):
            schedule_appointment_reminder(
                tenant_id,
                uid,
                result["starts_at"],
                business_name=profile.business_name,
            )
        return json.dumps(result)

    def _list_slots(self, args: dict[str, Any], tenant_id: str = DEFAULT_TENANT_ID, **_: Any) -> str:
        from platform.calendar import list_available_slots

        slots = list_available_slots(tenant_id, args.get("date", ""))
        return json.dumps({"date": args.get("date", ""), "slots": slots})

    def _payment_link(self, args: dict[str, Any], tenant_id: str, user_id: str, **_: Any) -> str:
        from platform.payments import create_payment_link

        url = create_payment_link(
            amount_cents=int(args.get("amount_cents", 0)),
            currency=args.get("currency", "eur"),
            description=args.get("description", "Payment"),
            tenant_id=tenant_id,
            user_id=args.get("user_id") or user_id,
        )
        return json.dumps({"payment_url": url}) if url else "Payment link could not be created."

    def _schedule_reminder(self, args: dict[str, Any], tenant_id: str, user_id: str, **_: Any) -> str:
        from platform.outbound import schedule_appointment_reminder

        profile = load_business_profile(tenant_id)
        job_id = schedule_appointment_reminder(
            tenant_id,
            args.get("user_id") or user_id,
            args.get("appointment_time", ""),
            hours_before=float(args.get("hours_before", 24)),
            business_name=profile.business_name,
        )
        return json.dumps({"scheduled_job_id": job_id, "status": "pending"})


def detect_intent(message: str) -> str:
    """Industry-agnostic intent detection."""
    lower = message.lower()
    if any(w in lower for w in ("status", "where am i", "my order", "my booking", "progress", "update")):
        return "case_status"
    if any(w in lower for w in ("upload", "document", "photo", "pdf", "form", "picture", "image")):
        return "document"
    if any(w in lower for w in ("book", "appointment", "reserve", "order", "buy", "quote", "price")):
        return "service_request"
    if any(w in lower for w in ("hi", "hello", "hey", "thanks", "hoi", "hallo")):
        return "greeting"
    return "general"
