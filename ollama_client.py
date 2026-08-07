"""Ollama LLM client — legacy module; prefer llm_client.py."""

from __future__ import annotations

import logging

import requests

from config import DEFAULT_TENANT_ID, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_NUM_PREDICT
from platform.business_profile import load_business_profile
from prompts import build_system_prompt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = build_system_prompt(load_business_profile(DEFAULT_TENANT_ID))


def generate_ollama(messages: list[dict[str, str]]) -> str:
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
        return resp.json().get("message", {}).get("content", "").strip()
    except Exception as exc:
        logger.error("Ollama request failed: %s", exc)
        return ""
