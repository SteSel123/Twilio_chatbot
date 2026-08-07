"""Unified LLM client — Ollama (dev) or OpenAI (production)."""

from __future__ import annotations

import logging

import requests

from config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_PREDICT,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)
from config import DEFAULT_TENANT_ID
from platform.business_profile import load_business_profile
from prompts import build_system_prompt

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = build_system_prompt(load_business_profile(DEFAULT_TENANT_ID))


def generate_response(
    user_message: str,
    internal_context: str,
    web_context: str,
    history: list[dict[str, str]],
    user_context: str = "",
    media_note: str = "",
    system_prompt: str | None = None,
) -> str:
    """Route to configured LLM provider."""
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return _openai_generate(
            user_message, internal_context, web_context, history, user_context, media_note, system_prompt
        )
    return _ollama_generate(
        user_message, internal_context, web_context, history, user_context, media_note, system_prompt
    )


def _build_user_content(
    user_message: str,
    internal_context: str,
    web_context: str,
    user_context: str,
    media_note: str,
) -> str:
    context_parts = []
    if user_context:
        context_parts.append("## Stored user & case data\n" + user_context)
    if internal_context:
        context_parts.append("## Internal documentation\n" + internal_context)
    if web_context:
        context_parts.append("## Web search results\n" + web_context)
    if not internal_context and not web_context:
        context_parts.append(
            "## Note\nNo internal docs or search results were found. "
            "Answer from general business knowledge and ask clarifying questions."
        )

    user_content = f"{chr(10).join(context_parts)}\n\n## User message\n{user_message}"
    if media_note:
        user_content += f"\n\n## Attachments\n{media_note}"
    user_content += (
        "\n\nFollow the workflow and output format in your instructions. "
        "Ask only 1–2 questions. Include a friendly time estimate."
    )
    return user_content


def _ollama_generate(
    user_message: str,
    internal_context: str,
    web_context: str,
    history: list[dict[str, str]],
    user_context: str,
    media_note: str,
    system_prompt: str | None,
) -> str:
    prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
    user_content = _build_user_content(user_message, internal_context, web_context, user_context, media_note)
    messages: list[dict[str, str]] = [{"role": "system", "content": prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": OLLAMA_NUM_PREDICT},
            },
            timeout=90,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "").strip()
        if content:
            return content
    except Exception as exc:
        logger.error("Ollama request failed: %s", exc)

    return _fallback_error()


def _openai_generate(
    user_message: str,
    internal_context: str,
    web_context: str,
    history: list[dict[str, str]],
    user_context: str,
    media_note: str,
    system_prompt: str | None,
) -> str:
    prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
    user_content = _build_user_content(user_message, internal_context, web_context, user_context, media_note)
    messages: list[dict[str, str]] = [{"role": "system", "content": prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})

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
                "max_tokens": 600,
                "temperature": 0.4,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content:
            return content
    except Exception as exc:
        logger.error("OpenAI request failed: %s", exc)

    return _fallback_error()


def _fallback_error() -> str:
    return (
        "I'm sorry — I couldn't reach the language model right now. "
        "Please try again in a moment, or ask to speak with a team member."
    )


def build_agent_user_content(
    user_message: str,
    internal_context: str,
    web_context: str,
    user_context: str = "",
    media_note: str = "",
) -> str:
    return _build_user_content(user_message, internal_context, web_context, user_context, media_note)
