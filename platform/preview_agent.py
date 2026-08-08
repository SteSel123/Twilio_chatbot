"""Agentic setup preview — reuses BusinessAgent RAG + LLM (no scripted templates)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from doc_loader import load_all_docs
from llm_client import build_agent_user_content, generate_response
from platform.business_profile import load_business_profile
from platform.consent import record_consent
from platform.i18n import detect_language, localized_system_prompt_addendum
from platform.preview_i18n import booking_date_label, normalize_locale, pt
from platform.leads import qualify_lead
from platform.llm_tools import generate_with_tools, openai_tool_calling_available
from platform.google_maps import get_maps_context_for_profile, message_needs_google_maps
from platform.mcp import ToolRegistry, detect_intent
from platform.preview_ui import (
    build_preview_payload,
    doc_files_for_business_bootstrap,
    doc_files_for_tenant_docs,
    doc_files_for_upload,
    turn_to_steps,
)
from platform.prompt_guard import strip_injection_attempts
from platform.tiers import tier_allows_web_search
from platform.verticals import get_vertical
from prompts import build_system_prompt
from rag.vector_store import vector_search
from user_data import UserDataStore, _storage_key

logger = logging.getLogger(__name__)

PREVIEW_USER_PREFIX = "preview:"

def opening_hours_question(locale: str = "nl") -> str:
    return pt("opening_hours_question", locale)

OPENING_HOURS_LLM_ADDENDUM = (
    "\n\nOPENING HOURS: The customer asks when you are open TODAY. "
    "Answer immediately with exact hours from Google Maps or the knowledge base (e.g. 'Vandaag open van 09:00 tot 18:00'). "
    "Never tell them to 'send their question' or that you will get back with hours later. "
    "If no hours are in the context, say honestly that hours are by appointment and give the phone number from the knowledge base."
)

_PHONE_RE = re.compile(
    r"\b(?:\+32[\s.-]?|0\d)[\d\s./-]{7,18}\d\b",
    re.I,
)


def _extract_phone_from_knowledge(knowledge: str) -> str:
    for match in _PHONE_RE.finditer(knowledge or ""):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 9:
            raw = match.group(0).strip()
            if raw.startswith("+") or raw.startswith("0"):
                return raw
    return ""


def compose_opening_hours_reply(
    *,
    business_name: str,
    industry: str,
    knowledge: str = "",
    opening_hours_today: str = "",
    weekday_descriptions: list[str] | None = None,
    google_maps_hours: bool = False,
    website_url: str = "",
    saved_doc: str = "",
    locale: str = "nl",
) -> tuple[str, list[dict]]:
    """Direct opening-hours answer — no LLM deflection."""
    from platform.commercial_tone import commercial_opening_answer, is_closed_hours_message
    from platform.setup_preview import _pick_hours_line, _pick_today_hours_line

    today = (opening_hours_today or "").strip()
    if not today and knowledge:
        today = (_pick_today_hours_line(knowledge) or _pick_hours_line(knowledge) or "").strip()

    files = doc_files_for_business_bootstrap(
        google_maps=google_maps_hours or "google maps" in knowledge.lower(),
        business_name=business_name,
        website_url=website_url,
        saved_doc=saved_doc,
    )
    loc = normalize_locale(locale)
    if google_maps_hours or "google maps" in knowledge.lower():
        trace = {
            "kind": "docs",
            "files": files,
            "searching": pt("maps_trace_searching", loc),
            "done": pt("maps_trace_done", loc),
            "note": pt("maps_trace_note", loc),
            "show_lock": True,
        }
    else:
        trace = {
            "kind": "docs",
            "files": files,
            "searching": pt("business_trace_searching", loc),
            "done": pt("business_trace_done", loc),
            "note": pt("business_trace_note", loc),
            "show_lock": True,
        }
    traces: list[dict] = [trace]

    name = business_name.strip() or pt("us_fallback", loc)
    if today or weekday_descriptions:
        reply = commercial_opening_answer(
            today_summary=today,
            business_name=business_name,
            industry=industry,
            weekday_descriptions=weekday_descriptions,
            locale=loc,
        )
        if "stuur je vraag door" not in reply.lower():
            return reply, traces

    if not today:
        phone = _extract_phone_from_knowledge(knowledge)
        if phone:
            reply = pt("opening_appointment_phone", loc, business=name, phone=phone)
        else:
            reply = pt("opening_appointment_no_phone", loc, business=name)
        return reply, traces

    if today and ":" in today and not is_closed_hours_message(today):
        reply = pt("opening_open", loc, business=name, hours=today)
        return reply, traces

    reply = pt("opening_by_appointment", loc, business=name)
    return reply, traces


def compose_upload_reply(
    *,
    knowledge: str,
    business_name: str,
    industry: str,
    source_name: str = "",
    saved_doc: str = "",
    locale: str = "nl",
) -> tuple[str, list[dict]] | None:
    """Direct answer from uploaded OCR text when prices or facts are parseable."""
    from platform.setup_preview import (
        _pick_energy_installation_row,
        _pick_fact_line,
        _pick_priced_item,
        _is_sensible_fact_line,
    )

    text = (knowledge or "").strip()
    if not text:
        return None

    industry_key = industry.lower()
    prefer = {
        "industrial": ["zonnepaneel", "storingsdienst", "preventief", "cnc", "onderhoud", "paneel"],
        "construction": ["warmtepomp", "installatie", "cv", "airco", "zonnepaneel"],
        "logistics": ["pallet", "transport", "express", "koel"],
        "financial": ["schade", "belasting", "advies", "expert"],
        "property": ["spoed", "lekkage", "beheer", "huur"],
    }.get(industry_key, [])
    loc = normalize_locale(locale)
    name = business_name.strip() or pt("us_fallback", loc)
    traces = [
        _doc_trace(
            industry_key,
            upload=True,
            source_name=source_name,
            saved_doc=saved_doc,
            locale=loc,
        )
    ]

    solar = _pick_energy_installation_row(text)
    if solar:
        count, price = solar
        from platform.preview_i18n import format_solar_panel_item

        item = format_solar_panel_item(count, loc)
        reply = pt("upload_reply_solar", loc, item=item, price=price)
        return reply, traces

    priced = _pick_priced_item(text, prefer=prefer, industry=industry_key)
    if priced:
        item, price = priced
        reply = pt("upload_reply_priced", loc, item=item, price=price)
        return reply, traces

    fact_line = _pick_fact_line(text)
    if fact_line and _is_sensible_fact_line(fact_line):
        reply = f"Hoi! {fact_line.rstrip('.')}. Wil je daar meer details over?"
        return reply, traces

    return None


UPLOAD_TURN_ADDENDUM = (
    "\n\nUPLOAD PREVIEW: The business owner uploaded an internal document. "
    "The customer question refers to content FROM THAT UPLOAD ONLY. "
    "Answer with concrete facts (prices, specs, conditions) from the uploaded document. "
    "Do not invent CNC errors or sector scenarios that are not in the document."
)


PREVIEW_PROMPT_ADDENDUM = (
    "\n\nPREVIEW MODE: You are demonstrating this WhatsApp assistant to the business owner. "
    "Be professional, concise, and B2B-appropriate. Answer from the knowledge base first. "
    "Structure replies: brief acknowledgment → concrete facts (prices, times, SLA if known) → one clear next step. "
    "Do not mention that you are an AI demo."
)


@dataclass
class PreviewTurnResult:
    reply: str
    traces: list[dict] = field(default_factory=list)
    intent: str = "general"
    tags: list[str] = field(default_factory=list)


def preview_user_id(tenant_id: str) -> str:
    return f"{PREVIEW_USER_PREFIX}{tenant_id}"


def _ensure_preview_consent(data_store: UserDataStore, scoped: str) -> None:
    record_consent(data_store, scoped)


def _response_tags(reply: str, industry: str) -> list[str]:
    tags: list[str] = []
    if "€" in reply:
        tags.append("Tarief / prijs")
    key = industry.lower()
    if key == "industrial":
        tags.append("Storing / onderhoud")
    elif key == "construction":
        tags.append("Intake / offerte")
    elif key == "logistics":
        tags.append("Levering / status")
    elif key == "financial":
        tags.append("Dossier / advies")
    elif key == "property":
        tags.append("Melding / planning")
    if re.search(r"\b(vandaag|morgen|uur|:\d{2})\b", reply, re.I):
        tags.append("Planning")
    return tags[:3] or ["Antwoord op basis van jouw data"]


def _doc_trace(
    industry: str,
    *,
    maps: bool = False,
    upload: bool = False,
    source_files: list[str] | None = None,
    docs_dir: Path | None = None,
    source_name: str = "",
    saved_doc: str = "",
    locale: str = "nl",
) -> dict:
    loc = normalize_locale(locale)
    if upload:
        return {
            "kind": "docs",
            "files": source_files
            or doc_files_for_upload(source_name=source_name, saved_doc=saved_doc),
            "searching": pt("upload_trace_searching", loc),
            "done": pt("upload_trace_done", loc),
            "note": pt("upload_trace_note", loc),
            "show_lock": True,
        }
    if maps:
        return {
            "kind": "docs",
            "files": source_files or ["Google Maps — openingstijden"],
            "searching": pt("maps_trace_searching", loc),
            "done": pt("maps_trace_done", loc),
            "note": pt("maps_trace_note", loc),
            "show_lock": True,
        }
    files = source_files
    if not files and docs_dir is not None:
        files = doc_files_for_tenant_docs(docs_dir)
    return {
        "kind": "docs",
        "files": files or ["Kennisbank"],
        "searching": "Kennisbank wordt geraadpleegd…",
        "done": "Documenten gelezen",
        "note": "Alleen zichtbaar voor jouw team — klanten zien nooit je bronbestanden.",
        "show_lock": True,
    }


def _web_trace(query: str, industry: str) -> dict:
    from platform.setup_preview import _web_search_context

    ctx = _web_search_context(industry, city="")
    return {
        "kind": "web",
        "query": query or ctx.get("query", ""),
        "searching": str(ctx.get("searching", "Actuele info wordt opgezocht…")),
        "done": str(ctx.get("done", "Sectorinfo toegevoegd")),
    }


def handle_preview_turn(
    agent,
    *,
    tenant_id: str,
    message: str,
    user_id: str | None = None,
    upload_source: bool = False,
    source_name: str = "",
    saved_doc: str = "",
    upload_knowledge: str = "",
) -> PreviewTurnResult:
    """One agentic turn for setup preview — real RAG + optional web + LLM."""
    profile = load_business_profile(tenant_id)
    uid = user_id or preview_user_id(tenant_id)
    message = strip_injection_attempts(message.strip())
    scoped = _storage_key(uid, tenant_id)
    _ensure_preview_consent(agent.data_store, scoped)

    lang = detect_language(message) if message else profile.language_default
    agent.data_store.set_language(scoped, lang)

    history = agent.memory.get_history(uid, tenant_id)
    user_context = agent.data_store.format_context_for_llm(scoped)
    documents = load_all_docs(profile.docs_dir)
    tools = ToolRegistry(agent.data_store, tenant_id=tenant_id)
    traces: list[dict] = []

    if upload_source and upload_knowledge.strip():
        internal_context = f"Geüpload document ({source_name or 'upload'}):\n{upload_knowledge.strip()}"
        traces.append(
            _doc_trace(
                profile.industry,
                upload=True,
                source_name=source_name,
                saved_doc=saved_doc,
            )
        )
    else:
        internal_context = vector_search(message, documents, tenant_id=tenant_id)
        if not internal_context:
            internal_context = tools.invoke(
                "searchBusinessDocs",
                {"query": message},
                tenant_id=tenant_id,
                user_id=uid,
            )
        if internal_context:
            traces.append(
                _doc_trace(
                    profile.industry,
                    upload=upload_source,
                    docs_dir=profile.docs_dir if not upload_source else None,
                    source_name=source_name,
                    saved_doc=saved_doc,
                )
            )

    used_maps = False
    maps_context = ""
    if message_needs_google_maps(message):
        maps_context = get_maps_context_for_profile(profile)
        if maps_context:
            used_maps = True
            if not any(t.get("kind") == "docs" for t in traces):
                traces.append(_doc_trace(profile.industry, maps=True))
            internal_context = f"{maps_context}\n\n{internal_context}".strip()

    web_context = ""
    web_query = ""
    skip_web = upload_source or bool(maps_context and message_needs_google_maps(message))
    if tier_allows_web_search(tenant_id) and not skip_web and agent._should_search_web(
        message, [(message, internal_context, 1.0)] if internal_context else [], history, tenant_id
    ):
        web_query = agent._build_search_query(message, history, uid, tenant_id)
        web_context = tools.invoke(
            "webSearch",
            {"query": web_query},
            tenant_id=tenant_id,
            user_id=uid,
        )
        if web_context:
            traces.append(_web_trace(web_query, profile.industry))

    intent = detect_intent(message)
    if intent in ("service_request", "general") and message:
        lead = qualify_lead(message, history)
        lead_ctx = tools.invoke(
            "qualifyLead",
            {"message": message, "user_id": uid},
            tenant_id=tenant_id,
            user_id=uid,
        )
        if lead_ctx:
            user_context = f"{user_context}\nLead score: {lead_ctx}".strip()

    system_prompt = build_system_prompt(profile, localized_system_prompt_addendum(lang))
    system_prompt += PREVIEW_PROMPT_ADDENDUM
    if message.strip().lower() in (
        opening_hours_question("nl").lower(),
        opening_hours_question("en").lower(),
        "wat zijn jullie openingstijden?",
        "hoe laat zijn jullie open?",
    ):
        system_prompt += OPENING_HOURS_LLM_ADDENDUM
    if upload_source:
        system_prompt += UPLOAD_TURN_ADDENDUM
    user_content = build_agent_user_content(message, internal_context, web_context, user_context, "")

    reply = ""
    if openai_tool_calling_available() and intent in ("service_request", "general"):

        def _tool_invoke(name: str, args: dict) -> str:
            return tools.invoke(
                name,
                {**args, "user_id": uid},
                tenant_id=tenant_id,
                user_id=uid,
            )

        reply, _ = generate_with_tools(
            system_prompt=system_prompt,
            user_content=user_content,
            history=history,
            tool_invoke=_tool_invoke,
        )

    if not reply:
        reply = generate_response(
            user_message=message,
            internal_context=internal_context,
            web_context=web_context,
            history=history,
            user_context=user_context,
            system_prompt=system_prompt,
        )

    # Preview: no disclaimer / feedback prompts in the bubble.
    reply = reply.split("\n\n_")[0].strip()
    reply = re.sub(r"\n*(Was this helpful|Was dit nuttig).*", "", reply, flags=re.I).strip()

    tags = _response_tags(reply, profile.industry)
    agent.memory.add_turn(uid, message, reply, tenant_id)

    return PreviewTurnResult(reply=reply, traces=traces, intent=intent, tags=tags)


def run_opening_hours_preview(
    agent,
    *,
    tenant_id: str,
    industry: str,
    business_name: str,
    source: str = "business",
    extra: dict | None = None,
    knowledge: str = "",
    opening_hours_today: str = "",
    weekday_descriptions: list[str] | None = None,
    google_maps_hours: bool = False,
    website_url: str = "",
    saved_doc: str = "",
    locale: str = "nl",
) -> dict:
    """Turn 1: opening hours from Google — then UI waits for owner upload."""
    uid = preview_user_id(tenant_id)
    agent.memory.clear(uid, tenant_id)

    extra = extra or {}
    loc = normalize_locale(locale or extra.get("locale"))
    reply, traces = compose_opening_hours_reply(
        business_name=business_name,
        industry=industry,
        knowledge=knowledge or extra.get("knowledge_full", ""),
        opening_hours_today=opening_hours_today or str(extra.get("opening_hours_today", "")),
        weekday_descriptions=weekday_descriptions,
        google_maps_hours=google_maps_hours or bool(extra.get("google_maps_hours")),
        website_url=website_url or str(extra.get("website_url", "")),
        saved_doc=saved_doc or str(extra.get("saved_doc", "")),
        locale=loc,
    )
    question = opening_hours_question(loc)
    turn = PreviewTurnResult(
        reply=reply,
        traces=traces,
        tags=_response_tags(reply, industry),
    )
    agent.memory.add_turn(uid, question, reply, tenant_id)
    conversation = turn_to_steps(
        question,
        turn.reply,
        industry=industry,
        traces=turn.traces,
        response_tags=turn.tags,
    )
    payload = build_preview_payload(
        business_name=business_name,
        industry=industry,
        conversation=conversation,
        source=source,
        doc_files=traces[0]["files"] if traces else [],
        extra=extra,
        locale=loc,
    )
    payload.update({
        "phase": "opening_hours",
        "await_upload": True,
        "progress_label": pt("progress_business", loc),
        "sample_question": question,
        "sample_answer": turn.reply,
    })
    return payload


def run_upload_follow_up_preview(
    agent,
    *,
    tenant_id: str,
    industry: str,
    business_name: str,
    extra: dict | None = None,
    source_name: str = "",
    saved_doc: str = "",
    knowledge: str = "",
) -> dict:
    """Turn 2: customer question derived from uploaded document content."""
    from platform.setup_preview import build_upload_customer_question

    uid = preview_user_id(tenant_id)
    extra = extra or {}
    loc = normalize_locale(extra.get("locale"))
    knowledge_text = knowledge or str(extra.get("knowledge_full", "")) or str(extra.get("knowledge_preview", ""))
    question = build_upload_customer_question(
        knowledge_text,
        business_name,
        industry,
        source_name=source_name or str(extra.get("source_name", "")),
        locale=loc,
    )

    src = source_name or str(extra.get("source_name", ""))
    doc = saved_doc or str(extra.get("saved_doc", ""))
    composed = compose_upload_reply(
        knowledge=knowledge_text,
        business_name=business_name,
        industry=industry,
        source_name=src,
        saved_doc=doc,
        locale=loc,
    )
    if composed:
        reply, traces = composed
        turn = PreviewTurnResult(
            reply=reply,
            traces=traces,
            tags=_response_tags(reply, industry),
        )
        agent.memory.add_turn(uid, question, reply, tenant_id)
    else:
        turn = handle_preview_turn(
            agent,
            tenant_id=tenant_id,
            message=question,
            user_id=uid,
            upload_source=True,
            source_name=src,
            saved_doc=doc,
            upload_knowledge=knowledge_text,
        )
    conversation = turn_to_steps(
        question,
        turn.reply,
        industry=industry,
        traces=turn.traces,
        response_tags=turn.tags,
    )
    payload = build_preview_payload(
        business_name=business_name,
        industry=industry,
        conversation=conversation,
        source="upload",
        doc_files=turn.traces[0]["files"] if turn.traces else [],
        extra=extra,
        locale=loc,
    )
    payload.update({
        "phase": "upload",
        "append": True,
        "await_upload": False,
        "progress_label": pt("progress_upload", loc),
        "sample_question": question,
        "sample_answer": turn.reply,
    })
    return payload


def _next_booking_day(locale: str = "nl"):
    from datetime import date, timedelta

    day = date.today() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    label = booking_date_label(day, locale)
    return day.isoformat(), label


def _service_hint_from_knowledge(knowledge: str, industry: str, locale: str = "nl") -> str:
    from platform.setup_preview import _pick_energy_installation_row, _pick_priced_item

    loc = normalize_locale(locale)
    text = (knowledge or "").strip()
    if not text:
        return pt("service_fallback", loc)

    solar = _pick_energy_installation_row(text)
    if solar:
        from platform.preview_i18n import format_solar_service_hint

        return format_solar_service_hint(solar[0], loc)

    priced = _pick_priced_item(text, industry=industry.lower())
    if priced:
        return priced[0]

    if "zonnepanelen" in text.lower():
        return pt("service_solar_installation", loc, item=pt("upload_stem_solar", loc))
    return pt("service_fallback", loc)


def _calendar_trace(
    *,
    provider: str,
    connected: bool,
    slot: str,
    date_label: str,
    customer_email: str = "",
    owner_email: str = "",
    invites: bool = False,
    locale: str = "nl",
) -> dict:
    loc = normalize_locale(locale)
    if invites and customer_email:
        done = pt("calendar_trace_invite_done", loc, date=date_label, slot=slot)
        note = pt("calendar_trace_invite_note", loc, email=customer_email)
    elif connected:
        done = pt("calendar_trace_invite_done", loc, date=date_label, slot=slot)
        note = f"{provider}."
    else:
        done = pt("calendar_trace_invite_done", loc, date=date_label, slot=slot)
        note = ""
    return {
        "kind": "calendar",
        "provider": provider,
        "searching": pt("calendar_trace_searching", loc, provider=provider),
        "done": done,
        "note": note,
        "show_lock": True,
    }


PREVIEW_CUSTOMER_EMAIL = "sophie.devriendt@gmail.com"


def compose_calendar_booking_turns(
    *,
    tenant_id: str,
    business_name: str,
    industry: str,
    knowledge: str = "",
    service_hint: str = "",
    google_connected: bool = False,
    preview_user: str = "",
    owner_email: str = "",
    locale: str = "nl",
) -> list[tuple[str, str, list[dict], list[str]]]:
    """Turn 3: ask customer email, then send calendar invites to klant + ondernemer."""
    from platform.calendar import book_appointment, list_available_slots

    loc = normalize_locale(locale)
    date_str, date_label = _next_booking_day(loc)
    slots = list_available_slots(tenant_id, date_str)
    slot = slots[0] if slots else "14:00"
    service = service_hint or _service_hint_from_knowledge(knowledge, industry, loc)
    provider = "Google Calendar"
    customer_email = PREVIEW_CUSTOMER_EMAIL
    owner = (owner_email or "").strip()
    owner_ok = owner and "@" in owner and not owner.lower().endswith("@pending.local")

    question1 = pt("calendar_q1", loc, date=date_label, service=service)
    reply1 = pt("calendar_r1", loc, date=date_label, slot=slot, service=service)

    question2 = pt("calendar_q2", loc, email=customer_email)
    traces2: list[dict] = []
    tag_appt = pt("tag_appointment", loc)
    tag_invite = pt("tag_invite_sent", loc)

    if google_connected and preview_user:
        result = book_appointment(
            tenant_id,
            preview_user,
            date=date_str,
            slot_time=slot,
            service=service,
            customer_name="Sophie (preview)",
            customer_email=customer_email,
            owner_email=owner if owner_ok else "",
            duration_minutes=60,
        )
        if result.get("ok"):
            traces2 = [
                _calendar_trace(
                    provider=provider,
                    connected=True,
                    slot=slot,
                    date_label=date_label,
                    customer_email=customer_email,
                    owner_email=owner if owner_ok else "",
                    invites=True,
                    locale=loc,
                )
            ]
            reply2 = pt(
                "calendar_r2",
                loc,
                email=customer_email,
                date=date_label,
                slot=slot,
                service=service,
            )
            tags2 = [tag_invite, tag_appt]
            return [
                (question1, reply1, [], [tag_appt]),
                (question2, reply2, traces2, tags2),
            ]

    traces2 = [
        _calendar_trace(
            provider=provider,
            connected=False,
            slot=slot,
            date_label=date_label,
            customer_email=customer_email,
            owner_email=owner if owner_ok else "",
            invites=True,
            locale=loc,
        )
    ]
    reply2 = pt(
        "calendar_r2_fallback",
        loc,
        email=customer_email,
        date=date_label,
        slot=slot,
    )
    return [
        (question1, reply1, [], [tag_appt]),
        (question2, reply2, traces2, [tag_invite]),
    ]


def compose_calendar_booking_reply(
    *,
    tenant_id: str,
    business_name: str,
    industry: str,
    knowledge: str = "",
    service_hint: str = "",
    google_connected: bool = False,
    preview_user: str = "",
    owner_email: str = "",
) -> tuple[str, str, list[dict]]:
    """Backward-compatible single-turn wrapper — first turn only."""
    turns = compose_calendar_booking_turns(
        tenant_id=tenant_id,
        business_name=business_name,
        industry=industry,
        knowledge=knowledge,
        service_hint=service_hint,
        google_connected=google_connected,
        preview_user=preview_user,
        owner_email=owner_email,
    )
    q, r, traces, _ = turns[0]
    return q, r, traces


def run_calendar_booking_preview(
    agent,
    *,
    tenant_id: str,
    industry: str,
    business_name: str,
    extra: dict | None = None,
    knowledge: str = "",
    google_connected: bool = False,
    owner_email: str = "",
) -> dict:
    """Turn 3: ask email, send calendar invites to customer + owner."""
    uid = preview_user_id(tenant_id)
    extra = extra or {}
    loc = normalize_locale(extra.get("locale"))
    knowledge_text = knowledge or str(extra.get("knowledge_full", ""))
    service_hint = _service_hint_from_knowledge(knowledge_text, industry, loc)
    from platform.calendar import list_available_slots

    date_str, _date_label = _next_booking_day(loc)
    slots = list_available_slots(tenant_id, date_str)
    slot = slots[0] if slots else "14:00"
    service = service_hint

    turns = compose_calendar_booking_turns(
        tenant_id=tenant_id,
        business_name=business_name,
        industry=industry,
        knowledge=knowledge_text,
        service_hint=service_hint,
        google_connected=google_connected,
        preview_user=uid,
        owner_email=owner_email or str(extra.get("owner_email", "")),
        locale=loc,
    )
    conversation: list[dict] = []
    last_q, last_r = "", ""
    for question, reply, traces, tags in turns:
        agent.memory.add_turn(uid, question, reply, tenant_id)
        conversation.extend(
            turn_to_steps(
                question,
                reply,
                industry=industry,
                traces=traces,
                response_tags=tags,
            )
        )
        last_q, last_r = question, reply

    payload = build_preview_payload(
        business_name=business_name,
        industry=industry,
        conversation=conversation,
        source="calendar",
        extra=extra,
        locale=loc,
    )
    payload.update({
        "phase": "calendar",
        "append": True,
        "await_upload": False,
        "google_connected": google_connected,
        "progress_label": pt("progress_calendar", loc),
        "sample_question": last_q,
        "sample_answer": last_r,
        "appointment_suggestion": pt("tag_invite_sent", loc),
        "appointment_slot": slot,
        "appointment_service": service,
    })
    return payload


def compose_appointment_reminder_message(
    *,
    business_name: str,
    service: str,
    slot: str,
    customer_name: str = "Sophie",
    locale: str = "nl",
) -> tuple[str, list[dict]]:
    """Step 4: proactive reminder that the customer has an appointment today."""
    loc = normalize_locale(locale)
    name = business_name.strip() or pt("us_fallback", loc)
    message = pt(
        "reminder_message",
        loc,
        name=customer_name,
        slot=slot,
        business=name,
        service=service,
    )
    traces = [
        {
            "kind": "reminder",
            "searching": pt("reminder_trace_searching", loc),
            "done": pt("reminder_trace_done", loc),
            "note": pt("reminder_trace_note", loc),
        }
    ]
    return message, traces


def run_appointment_reminder_preview(
    agent,
    *,
    tenant_id: str,
    industry: str,
    business_name: str,
    extra: dict | None = None,
    service_hint: str = "",
    appointment_slot: str = "",
) -> dict:
    """Step 4: automatic same-day appointment reminder."""
    from platform.calendar import list_available_slots
    from platform.preview_ui import proactive_message_to_steps

    uid = preview_user_id(tenant_id)
    extra = extra or {}
    loc = normalize_locale(extra.get("locale"))
    date_str, _date_label = _next_booking_day(loc)
    slot = appointment_slot or extra.get("appointment_slot") or ""
    if not slot:
        slots = list_available_slots(tenant_id, date_str)
        slot = slots[0] if slots else "14:00"
    service = service_hint or extra.get("appointment_service") or pt("service_appointment", loc)

    message, traces = compose_appointment_reminder_message(
        business_name=business_name,
        service=service,
        slot=slot,
        locale=loc,
    )
    agent.memory.add_turn(uid, "[automated reminder]", message, tenant_id)
    conversation = proactive_message_to_steps(
        message,
        traces=traces,
        response_tags=[pt("tag_reminder", loc)],
        banner=pt("proactive_banner", loc),
        locale=loc,
    )
    payload = build_preview_payload(
        business_name=business_name,
        industry=industry,
        conversation=conversation,
        source="reminder",
        extra=extra,
        locale=loc,
    )
    payload.update({
        "phase": "reminder",
        "append": True,
        "await_upload": False,
        "progress_label": pt("progress_reminder", loc),
        "sample_question": "",
        "sample_answer": message,
    })
    return payload


def _google_review_label(business_name: str, review_url: str = "") -> str:
    if review_url and "google" in review_url.lower():
        return "Google"
    name = business_name.strip()
    return f"Google ({name})" if name else "Google"


def _resolve_review_url(
    *,
    review_url: str = "",
    extra: dict | None = None,
    knowledge: str = "",
) -> str:
    """Profile URL, write-review from place id, Google Maps URI, or URL in knowledge."""
    from platform.google_maps import build_google_review_url

    extra = extra or {}
    place_id = str(extra.get("place_id") or "")
    maps_uri = str(extra.get("google_maps_uri") or "")
    built = build_google_review_url(place_id=place_id, google_maps_uri=maps_uri)
    if built:
        return built
    for candidate in (
        review_url,
        str(extra.get("review_url") or ""),
        maps_uri,
    ):
        if candidate and str(candidate).startswith("http"):
            return str(candidate).strip()
    match = re.search(r"\*\*Google Maps URL:\*\*\s*(https?://\S+)", knowledge or "")
    if match:
        return match.group(1).rstrip(").,")
    return ""


def compose_google_review_turn(
    *,
    business_name: str,
    review_url: str = "",
    customer_name: str = "Sophie",
    locale: str = "nl",
    knowledge: str = "",
    extra: dict | None = None,
    service_hint: str = "",
) -> tuple[str, str, str, list[dict]]:
    """Step 5: business asks if all went well, customer confirms, bot asks for review."""
    loc = normalize_locale(locale)
    name = business_name.strip() or pt("us_fallback", loc)
    service = (service_hint or "").strip() or pt("review_service_fallback", loc)
    url = _resolve_review_url(review_url=review_url, extra=extra, knowledge=knowledge)
    platform = _google_review_label(business_name, url)

    ask_message = pt(
        "review_followup_ask",
        loc,
        name=customer_name,
        business=name,
        service=service,
    )
    customer_confirm = pt("review_question", loc)
    if url:
        review_reply = pt(
            "review_reply_intro",
            loc,
            name=customer_name,
            platform=platform,
            business=name,
        )
        trace_note = pt("review_trace_note_link", loc, business=name)
    else:
        review_reply = pt(
            "review_reply",
            loc,
            name=customer_name,
            platform=platform,
            business=name,
        )
        trace_note = pt("review_trace_note", loc, platform=platform)
    traces = [
        {
            "kind": "review",
            "searching": pt("review_trace_searching", loc),
            "done": pt("review_trace_done", loc),
            "note": trace_note,
        }
    ]
    return ask_message, customer_confirm, review_reply, traces


def run_google_review_preview(
    agent,
    *,
    tenant_id: str,
    industry: str,
    business_name: str,
    extra: dict | None = None,
    review_url: str = "",
) -> dict:
    """Step 5: ask customer for a Google review after the visit."""
    from platform.business_profile import load_business_profile

    uid = preview_user_id(tenant_id)
    extra = extra or {}
    loc = normalize_locale(extra.get("locale"))
    profile = load_business_profile(tenant_id)
    knowledge_text = str(extra.get("knowledge_full") or extra.get("knowledge_preview") or "")
    url = _resolve_review_url(
        review_url=review_url or extra.get("review_url") or profile.review_url or "",
        extra=extra,
        knowledge=knowledge_text,
    )
    service_hint = str(
        extra.get("appointment_service") or extra.get("service_hint") or ""
    )

    ask_message, customer_confirm, review_reply, traces = compose_google_review_turn(
        business_name=business_name,
        review_url=url,
        locale=loc,
        knowledge=knowledge_text,
        extra=extra,
        service_hint=service_hint,
    )
    agent.memory.add_turn(uid, customer_confirm, review_reply, tenant_id)
    from platform.preview_ui import review_flow_to_steps

    conversation = review_flow_to_steps(
        ask_message=ask_message,
        customer_confirm=customer_confirm,
        review_reply=review_reply,
        traces=traces,
        response_tags=[pt("tag_review", loc)],
        customer_done=pt("review_customer_done", loc),
    )
    if url:
        for step in reversed(conversation):
            if step.get("type") == "bot":
                step["review_url"] = url
                step["review_link_label"] = pt("review_link_label", loc)
                step["review_link_detail"] = pt("review_link_detail", loc, business=business_name)
                break
    payload = build_preview_payload(
        business_name=business_name,
        industry=industry,
        conversation=conversation,
        source="review",
        extra=extra,
        locale=loc,
    )
    payload.update({
        "phase": "review",
        "append": True,
        "await_upload": False,
        "progress_label": pt("progress_review", loc),
        "sample_question": customer_confirm,
        "sample_answer": review_reply,
        "review_url": url,
    })
    if url:
        payload["review_link_label"] = pt("review_link_label", loc)
        payload["review_link_detail"] = pt("review_link_detail", loc, business=business_name)
    return payload
