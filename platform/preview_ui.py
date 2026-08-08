"""Map real agent traces to setup-page WhatsApp UI steps."""

from __future__ import annotations

from pathlib import Path

from platform.preview_i18n import normalize_locale, pt


def doc_files_for_business_bootstrap(
    *,
    google_maps: bool,
    business_name: str = "",
    website_url: str = "",
    saved_doc: str = "",
) -> list[str]:
    """Labels for Google/online bootstrap — no fake PDF names."""
    from platform.setup_preview import _doc_files_for_business_lookup

    items = _doc_files_for_business_lookup(
        google_maps=google_maps,
        business_name=business_name,
        website_url=website_url,
    )
    if saved_doc:
        label = Path(saved_doc.replace("\\", "/")).name
        if label and label not in items:
            items = [label, *items]
    return items[:3]


def doc_files_for_upload(*, source_name: str = "", saved_doc: str = "") -> list[str]:
    """Labels for owner upload step."""
    items: list[str] = []
    if source_name:
        items.append(Path(source_name).name)
    if saved_doc:
        label = Path(saved_doc.replace("\\", "/")).name
        if label and label not in items:
            items.append(label)
    return items or ["Geüpload document"]


def doc_files_for_tenant_docs(docs_dir: Path | str, *, limit: int = 3) -> list[str]:
    """Actual filenames from the tenant knowledge folder."""
    root = Path(docs_dir)
    if not root.is_dir():
        return ["Kennisbank"]
    files = sorted(
        (p for p in root.iterdir() if p.is_file() and p.suffix.lower() in {".md", ".txt", ".pdf"}),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [p.name for p in files[:limit]] or ["Kennisbank"]


def turn_to_steps(
    customer_message: str,
    reply: str,
    *,
    industry: str,
    traces: list[dict],
    response_tags: list[str] | None = None,
) -> list[dict]:
    """Convert one agent preview turn into animated setup.html steps."""
    steps: list[dict] = [{"type": "customer", "text": customer_message}]

    for trace in traces:
        kind = trace.get("kind", "")
        if kind == "docs":
            files = trace.get("files") or []
            steps.append({
                "type": "internal_docs",
                "doc_files": files,
                "doc_searching": trace.get("searching", "Bronnen worden geraadpleegd…"),
                "doc_done": trace.get("done", "Bronnen gelezen"),
                "doc_note": trace.get("note", ""),
                "doc_show_lock": trace.get("show_lock", True),
            })
        elif kind == "web":
            steps.append({
                "type": "web_search",
                "query": trace.get("query", ""),
                "searching": trace.get("searching", "Actuele info wordt opgezocht…"),
                "done": trace.get("done", "Sectorinfo toegevoegd"),
            })
        elif kind == "note":
            steps.append({"type": "internal_note", "text": trace.get("text", "")})
        elif kind == "calendar":
            steps.append({
                "type": "internal_calendar",
                "provider": trace.get("provider", "Google Calendar"),
                "searching": trace.get("searching", "Agenda wordt geraadpleegd…"),
                "done": trace.get("done", "Afspraak ingepland"),
                "note": trace.get("note", ""),
                "show_lock": trace.get("show_lock", True),
            })
        elif kind == "reminder":
            steps.append({
                "type": "internal_reminder",
                "searching": trace.get("searching", "Herinnering wordt ingepland…"),
                "done": trace.get("done", "Automatisch bericht verstuurd"),
                "note": trace.get("note", ""),
            })
        elif kind == "review":
            steps.append({
                "type": "internal_review",
                "searching": trace.get("searching", "Google review-link wordt klaargezet…"),
                "done": trace.get("done", "Review-verzoek klaar"),
                "note": trace.get("note", ""),
            })

    steps.append({
        "type": "bot",
        "text": reply,
        "tags": response_tags or [],
    })
    return steps


def review_flow_to_steps(
    *,
    ask_message: str,
    customer_confirm: str,
    review_reply: str,
    traces: list[dict],
    response_tags: list[str] | None = None,
    customer_done: str = "",
) -> list[dict]:
    """Step 5: business asks first, customer confirms, then review link, then goodbye."""
    steps: list[dict] = [{"type": "bot", "text": ask_message}]
    steps.append({"type": "customer", "text": customer_confirm})

    for trace in traces:
        kind = trace.get("kind", "")
        if kind == "review":
            steps.append({
                "type": "internal_review",
                "searching": trace.get("searching", "Google review-link wordt klaargezet…"),
                "done": trace.get("done", "Review-verzoek klaar"),
                "note": trace.get("note", ""),
            })

    steps.append({
        "type": "bot",
        "text": review_reply,
        "tags": response_tags or [],
    })
    if customer_done:
        steps.append({"type": "customer", "text": customer_done})
    return steps


def proactive_message_to_steps(
    message: str,
    *,
    traces: list[dict] | None = None,
    response_tags: list[str] | None = None,
    banner: str = "",
    locale: str = "nl",
) -> list[dict]:
    """Proactive outbound WhatsApp — no customer message first."""
    loc = normalize_locale(locale)
    steps: list[dict] = [{"type": "proactive_banner", "text": banner or pt("proactive_banner", loc)}]
    for trace in traces or []:
        kind = trace.get("kind", "")
        if kind == "reminder":
            steps.append({
                "type": "internal_reminder",
                "searching": trace.get("searching", "Herinnering wordt ingepland…"),
                "done": trace.get("done", "Automatisch bericht verstuurd"),
                "note": trace.get("note", ""),
            })
    steps.append({
        "type": "bot",
        "text": message,
        "tags": response_tags or ["Herinnering afspraak"],
        "proactive": True,
    })
    return steps


def build_preview_payload(
    *,
    business_name: str,
    industry: str,
    conversation: list[dict],
    source: str,
    doc_files: list[str] | None = None,
    extra: dict | None = None,
    locale: str = "nl",
) -> dict:
    loc = normalize_locale(locale or (extra or {}).get("locale"))
    progress = {
        "business": pt("progress_business", loc),
        "upload": pt("progress_upload", loc),
        "calendar": pt("progress_calendar", loc),
        "reminder": pt("progress_reminder", loc),
        "review": pt("progress_review", loc),
        "demo": pt("progress_upload", loc),
    }.get(source, pt("progress_upload", loc))

    payload = {
        "business_name": business_name,
        "source": source,
        "conversation": conversation,
        "doc_files": doc_files or [],
        "progress_label": progress,
        "progress_steps": max(4, min(8, len(conversation))),
        "preview_mode": "agentic",
    }
    if extra:
        payload.update(extra)
    if not payload.get("doc_files") and payload.get("conversation"):
        for step in payload["conversation"]:
            if step.get("type") == "internal_docs" and step.get("doc_files"):
                payload["doc_files"] = step["doc_files"]
                break
    return payload
