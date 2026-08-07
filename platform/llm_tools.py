"""OpenAI function-calling tools for booking and quotes."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

logger = logging.getLogger(__name__)

OPENAI_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "listAvailableSlots",
            "description": "List free appointment times on a given date (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string", "description": "Date YYYY-MM-DD"}},
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bookAppointment",
            "description": "Book an appointment for the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM 24h"},
                    "service": {"type": "string"},
                    "customer_name": {"type": "string"},
                },
                "required": ["date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "qualifyLead",
            "description": "Score customer interest for sales follow-up.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createPaymentLink",
            "description": "Create a Stripe payment link (amount in euro cents).",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_cents": {"type": "integer"},
                    "description": {"type": "string"},
                },
                "required": ["amount_cents", "description"],
            },
        },
    },
]


def openai_tool_calling_available() -> bool:
    return LLM_PROVIDER == "openai" and bool(OPENAI_API_KEY)


def generate_with_tools(
    *,
    system_prompt: str,
    user_content: str,
    history: list[dict[str, str]],
    tool_invoke: Callable[[str, dict[str, Any]], str],
    max_rounds: int = 3,
) -> tuple[str, list[dict[str, str]]]:
    """Run OpenAI chat with tool loop. Returns (reply, tool_traces)."""
    if not openai_tool_calling_available():
        return "", []

    import requests

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    traces: list[dict[str, str]] = []

    for _ in range(max_rounds):
        try:
            resp = requests.post(
                f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": messages,
                    "tools": OPENAI_AGENT_TOOLS,
                    "tool_choice": "auto",
                    "max_tokens": 600,
                    "temperature": 0.4,
                },
                timeout=45,
            )
            resp.raise_for_status()
            choice = resp.json()["choices"][0]["message"]
        except Exception as exc:
            logger.error("Tool-calling request failed: %s", exc)
            return "", traces

        tool_calls = choice.get("tool_calls") or []
        if not tool_calls:
            content = (choice.get("content") or "").strip()
            return content, traces

        messages.append(choice)
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = tool_invoke(name, args)
            traces.append({"tool": name, "result": result[:500]})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": result,
                }
            )

    return "", traces
