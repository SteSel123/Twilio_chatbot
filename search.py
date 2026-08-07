"""Internet search via Tavily with DuckDuckGo fallback."""

from __future__ import annotations

import logging
from typing import Any

import requests

from config import MAX_SEARCH_CONTEXT_CHARS, MAX_SEARCH_RESULTS, TAVILY_API_KEY, TAVILY_SEARCH_DEPTH

logger = logging.getLogger(__name__)


def search_tavily(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[dict[str, str]]:
    if not TAVILY_API_KEY:
        return []

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(
            query=query,
            search_depth=TAVILY_SEARCH_DEPTH,
            max_results=max_results,
            include_answer=True,
        )
        results: list[dict[str, str]] = []
        if response.get("answer"):
            results.append({"title": "Tavily summary", "content": response["answer"], "url": ""})
        for item in response.get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "url": item.get("url", ""),
                }
            )
        return results
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return []


def search_duckduckgo(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[dict[str, str]]:
    """Lightweight fallback when Tavily is unavailable."""
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        results: list[dict[str, str]] = []

        abstract = data.get("AbstractText") or data.get("Abstract", "")
        if abstract:
            results.append(
                {
                    "title": data.get("Heading", "DuckDuckGo"),
                    "content": abstract,
                    "url": data.get("AbstractURL", ""),
                }
            )

        for topic in data.get("RelatedTopics", [])[: max_results - len(results)]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(
                    {
                        "title": "Related",
                        "content": topic["Text"],
                        "url": topic.get("FirstURL", ""),
                    }
                )
        return results
    except Exception as exc:
        logger.warning("DuckDuckGo fallback failed: %s", exc)
        return []


def web_search(query: str) -> list[dict[str, str]]:
    """Search the web; prefer Tavily, fall back to DuckDuckGo."""
    results = search_tavily(query)
    if results:
        return results
    return search_duckduckgo(query)


def format_search_context(results: list[dict[str, str]], max_chars: int = MAX_SEARCH_CONTEXT_CHARS) -> str:
    if not results:
        return ""

    parts: list[str] = []
    total = 0
    for item in results:
        block = f"- **{item.get('title', 'Source')}**"
        if item.get("url"):
            block += f" ({item['url']})"
        block += f"\n  {item.get('content', '').strip()}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)

    return "\n".join(parts)
