"""SMB WhatsApp business assistant agent."""

from __future__ import annotations

import json
import logging
import re
import time

from config import DEFAULT_TENANT_ID
from doc_loader import load_all_docs
from document_storage import DocumentStorage
from llm_client import build_agent_user_content, generate_response
from memory import ConversationMemory
from patterns import SERVICE_TRIGGERS, SERVICE_TYPE_PATTERN, TOPIC_PATTERN
from platform.business_profile import load_business_profile
from platform.consent import consent_message, has_consent, is_consent_response, record_consent
from platform.feedback import (
    clear_pending_feedback,
    get_pending_feedback,
    is_feedback_response,
    record_feedback,
    set_pending_feedback,
)
from platform.gdpr import erase_user_data, export_user_data
from platform.google_maps import get_maps_context_for_profile, message_needs_google_maps
from platform.handoff import request_handoff, wants_handoff
from platform.analytics import record_lead, record_message
from platform.leads import qualify_lead
from platform.media_ai import process_saved_media
from platform.tiers import check_conversation_allowed, tier_allows_web_search
from platform.i18n import detect_language, localized_system_prompt_addendum, t
from platform.llm_tools import generate_with_tools, openai_tool_calling_available
from platform.mcp import ToolRegistry, detect_intent
from platform.observability import end_span, log_structured, start_span
from platform.prompt_guard import strip_injection_attempts
from platform.retention import apply_retention_to_store
from prompts import build_system_prompt
from rag.vector_store import vector_search
from storage import get_data_store
from user_data import UserDataStore, _storage_key

logger = logging.getLogger(__name__)

RESET_COMMANDS = {"reset", "clear", "start over", "new conversation"}
GDPR_EXPORT_COMMANDS = {"export my data", "download my data", "gdpr export", "export data"}
GDPR_DELETE_COMMANDS = {"delete my data", "erase my data", "gdpr delete", "remove my data"}
SMALL_TALK = re.compile(
    r"^(hi|hello|hey|thanks|thank you|ok|okay|bye|goodbye|hoi|hallo|dag)[!.?\s]*$",
    re.I,
)
RESCHEDULE_PATTERN = re.compile(r"^\s*reschedule\s*$", re.I)
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


class BusinessAgent:
    """Generic WhatsApp assistant for any small business."""

    def __init__(
        self,
        memory: ConversationMemory | None = None,
        data_store: UserDataStore | None = None,
        document_storage: DocumentStorage | None = None,
    ):
        self.memory = memory or ConversationMemory()
        self.data_store = data_store or get_data_store()
        self.document_storage = document_storage or DocumentStorage(self.data_store)
        self._documents: dict[str, str] = {}

    def _profile(self, tenant_id: str):
        return load_business_profile(tenant_id)

    def reload_docs(self, tenant_id: str = DEFAULT_TENANT_ID) -> None:
        profile = self._profile(tenant_id)
        self._documents = load_all_docs(profile.docs_dir)
        from rag.vector_store import reindex_documents

        reindex_documents(profile.docs_dir, tenant_id)

    def _should_search_web(self, message: str, doc_hits: list, history: list[dict[str, str]], tenant_id: str) -> bool:
        if self._is_intake_message(message) and doc_hits:
            return False
        lower = message.lower()
        profile = self._profile(tenant_id)
        if any(w in lower for w in ("latest", "current", "2024", "2025", "2026", "official", "update", "price", "cost", "how much", "website", "link", "hours", "open")):
            return True
        if len(doc_hits) < 1:
            return True
        if len(doc_hits) >= 2 and not history:
            return False
        return any(w in lower for w in SERVICE_TRIGGERS) and len(doc_hits) < 2

    def _is_intake_message(self, message: str) -> bool:
        lower = message.lower()
        has_topic = bool(TOPIC_PATTERN.search(message))
        action_words = ("book", "order", "buy", "need", "want", "looking", "quote", "reserve")
        has_action = any(w in lower for w in action_words)
        return has_topic and has_action

    def _is_small_talk(self, message: str) -> bool:
        return bool(SMALL_TALK.match(message.strip()))

    def _handle_reschedule(
        self,
        tools: ToolRegistry,
        *,
        tenant_id: str,
        user_id: str,
        correlation_id: str,
        lang: str,
    ) -> str:
        from datetime import date, timedelta

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        raw = tools.invoke(
            "listAvailableSlots",
            {"date": tomorrow},
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
        )
        try:
            slots = json.loads(raw).get("slots", [])
        except (json.JSONDecodeError, TypeError):
            slots = []
        if lang == "en":
            if slots:
                return (
                    f"Sure — available times tomorrow ({tomorrow}): {', '.join(slots)}. "
                    "Which time works for you?"
                )
            return (
                "I couldn't find open slots tomorrow. Send another date (YYYY-MM-DD) "
                "and I'll check again."
            )
        if slots:
            return (
                f"Geen probleem — morgen ({tomorrow}) zijn deze tijden vrij: {', '.join(slots)}. "
                "Welke past voor jou?"
            )
        return (
            "Ik zie morgen geen vrije tijden. Stuur een andere datum (YYYY-MM-DD) "
            "en ik kijk opnieuw."
        )

    def _heuristic_tool_notes(
        self,
        message: str,
        tools: ToolRegistry,
        *,
        tenant_id: str,
        user_id: str,
        correlation_id: str,
    ) -> str:
        lower = message.lower()
        notes: list[str] = []
        date_m = DATE_PATTERN.search(message)
        if date_m and any(w in lower for w in ("slot", "available", "free", "vrij", "tijd", "uur")):
            notes.append(
                tools.invoke(
                    "listAvailableSlots",
                    {"date": date_m.group(1)},
                    tenant_id=tenant_id,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
            )
        time_m = re.search(r"(\d{1,2}:\d{2})", message)
        if date_m and time_m and any(w in lower for w in ("book", "reserve", "afspraak", "plan", "inplannen")):
            notes.append(
                tools.invoke(
                    "bookAppointment",
                    {"date": date_m.group(1), "time": time_m.group(1)},
                    tenant_id=tenant_id,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
            )
        return "\n".join(n for n in notes if n)

    def _notify_owner_live(
        self,
        *,
        tenant_id: str,
        profile,
        message: str,
        reply: str,
        intent: str,
        appointment_note: str = "",
    ) -> None:
        if intent not in ("service_request", "case_status"):
            return
        try:
            from platform.onboarding import get_setup_email
            from platform.owner_email import send_owner_summary

            email = get_setup_email(tenant_id)
            if not email or email.endswith("@pending.local"):
                return
            send_owner_summary(
                to_email=email,
                business_name=profile.business_name,
                question=message[:800],
                answer=reply[:800],
                summary=f"Live WhatsApp-gesprek · intent={intent}",
                appointment=appointment_note,
            )
        except Exception as exc:
            logger.warning("Owner notification failed for %s: %s", tenant_id, exc)

    def _topic_from_history(self, history: list[dict[str, str]]) -> str:
        for turn in reversed(history):
            if turn.get("role") != "user":
                continue
            match = TOPIC_PATTERN.search(turn.get("content", ""))
            if match:
                return match.group(0)
        return ""

    def _topic_from_context(self, user_id: str, tenant_id: str) -> str:
        state = self.data_store.get_case_state(_storage_key(user_id, tenant_id))
        return state.get("country", "") or state.get("topic", "")

    def _build_search_query(self, message: str, history: list[dict[str, str]], user_id: str, tenant_id: str) -> str:
        profile = self._profile(tenant_id)
        topic_match = TOPIC_PATTERN.search(message)
        topic = (
            topic_match.group(0)
            if topic_match
            else self._topic_from_context(user_id, tenant_id) or self._topic_from_history(history)
        )
        service_match = SERVICE_TYPE_PATTERN.search(message)
        service = service_match.group(0) if service_match else ""

        base = message.strip()
        parts = [profile.business_name, profile.industry, topic, service, base]
        return " ".join(p for p in parts if p)

    def handle_message(
        self,
        user_id: str,
        message: str,
        media_items: list[dict[str, str]] | None = None,
        *,
        correlation_id: str = "",
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> str:
        profile = self._profile(tenant_id)
        message = strip_injection_attempts(message.strip())
        media_items = media_items or []
        scoped = _storage_key(user_id, tenant_id)
        log_prefix = f"[{correlation_id}] " if correlation_id else ""

        apply_retention_to_store(self.data_store, scoped)

        feedback_rating = is_feedback_response(message)
        if feedback_rating is not None:
            pending_cid = get_pending_feedback(user_id) or correlation_id
            record_feedback(self.data_store, scoped, feedback_rating, pending_cid)
            clear_pending_feedback(user_id)
            lang = self.data_store.get_language(scoped)
            return "Thank you for your feedback!" if lang == "en" else "Bedankt voor je feedback!"

        lang = detect_language(message) if message else self.data_store.get_language(scoped) or profile.language_default
        if message:
            self.data_store.set_language(scoped, lang)

        lower_msg = message.lower()
        if lower_msg in GDPR_EXPORT_COMMANDS:
            data = export_user_data(user_id, tenant_id)
            summary = json.dumps(data, indent=2, default=str)[:3000]
            return f"{t('gdpr_export', lang)}\n\n```\n{summary}\n```"

        if lower_msg in GDPR_DELETE_COMMANDS:
            erase_user_data(user_id, tenant_id)
            return t("gdpr_delete", lang)

        if not has_consent(self.data_store, scoped):
            if is_consent_response(message):
                record_consent(self.data_store, scoped)
                return profile.welcome_message + "\n\n" + t("disclaimer", lang)
            return consent_message(lang, business_name=profile.business_name)

        allowed, tier_msg = check_conversation_allowed(tenant_id)
        if not allowed and message:
            return tier_msg

        if not message and not media_items:
            return profile.welcome_message

        if message.lower() in RESET_COMMANDS:
            self.memory.clear(user_id, tenant_id)
            self.data_store.clear_user(scoped)
            return profile.welcome_message

        if wants_handoff(message):
            ctx = self.data_store.get_case_state(scoped)
            topic = ctx.get("topic", "") or ctx.get("country", "")
            service = ctx.get("service", "") or ctx.get("visa_type", "")
            summary = f"Topic: {topic}, Service: {service}".strip(", ")
            request_handoff(user_id, tenant_id, summary)
            return t("handoff", lang)

        tools = ToolRegistry(self.data_store, tenant_id=tenant_id)

        if RESCHEDULE_PATTERN.match(message):
            reply = self._handle_reschedule(
                tools,
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=correlation_id,
                lang=lang,
            )
            self.memory.add_turn(user_id, message, reply, tenant_id)
            return reply + t("disclaimer", lang)

        self.data_store.purge_expired()
        expired_note = ""
        if self.data_store.is_expired(scoped):
            self.data_store.clear_user(scoped)
            expired_note = (
                "Your previous session expired. Please share your details again.\n\n"
                if lang == "en"
                else "Je vorige sessie is verlopen. Deel je gegevens opnieuw.\n\n"
            )

        if self._is_small_talk(message) and not media_items:
            reply = profile.welcome_message
            self.memory.add_turn(user_id, message or "hi", reply, tenant_id)
            return reply

        saved_files: list[str] = []
        media_types: list[str] = []
        for item in media_items:
            url = item.get("url", "")
            content_type = item.get("content_type", "")
            if url:
                name = self.document_storage.save_twilio_media(user_id, url, content_type)
                if name:
                    saved_files.append(name)
                    media_types.append(content_type)

        media_analysis = ""
        if saved_files:
            media_analysis = process_saved_media(saved_files, media_types, tenant_id)
            if media_analysis and not message:
                message = media_analysis
            elif media_analysis:
                message = f"{message}\n\n{media_analysis}"
        elif saved_files and not message:
            message = f"[Customer uploaded: {', '.join(saved_files)}]"

        self.data_store.extract_fields_from_message(scoped, message)
        self.data_store.infer_case_updates(scoped, message)

        history = self.memory.get_history(user_id, tenant_id)
        user_context = self.data_store.format_context_for_llm(scoped)
        self._documents = load_all_docs(profile.docs_dir)

        t0 = time.perf_counter()
        record_message(
            tenant_id,
            user_id,
            "inbound",
            intent=detect_intent(message),
            message_preview=message,
        )

        doc_span = start_span("doc_search")
        internal_context = vector_search(message, self._documents, tenant_id=tenant_id)
        if not internal_context:
            internal_context = tools.invoke(
                "searchBusinessDocs",
                {"query": message},
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=correlation_id,
            )
        end_span(doc_span)

        maps_context = ""
        if message_needs_google_maps(message):
            maps_span = start_span("google_maps")
            maps_context = get_maps_context_for_profile(profile)
            end_span(maps_span)
            if maps_context:
                internal_context = (
                    f"{maps_context}\n\n{internal_context}".strip()
                    if internal_context
                    else maps_context
                )

        doc_hits = [(message, internal_context, 1.0)] if internal_context else []
        web_context = ""
        skip_web_for_maps = bool(maps_context and message_needs_google_maps(message))
        if (
            tier_allows_web_search(tenant_id)
            and not skip_web_for_maps
            and self._should_search_web(message, doc_hits, history, tenant_id)
        ):
            query = self._build_search_query(message, history, user_id, tenant_id)
            web_span = start_span("web_search")
            web_context = tools.invoke(
                "webSearch",
                {"query": query},
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=correlation_id,
            )
            end_span(web_span)

        intent = detect_intent(message)
        log_structured("intent_detected", intent=intent, user_id=user_id, tenant_id=tenant_id)

        lead_context = ""
        if intent in ("service_request", "general") and message:
            lead = qualify_lead(message, history)
            record_lead(
                tenant_id,
                user_id,
                interest=lead["interest"],
                budget=lead["budget"],
                urgency=lead["urgency"],
                score=lead["score"],
                labels=lead["labels"],
            )
            lead_context = tools.invoke(
                "qualifyLead",
                {"message": message, "user_id": user_id},
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=correlation_id,
            )

        if intent == "case_status":
            status = tools.invoke(
                "getCustomerContext",
                {"user_id": user_id, "tenant_id": tenant_id},
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=correlation_id,
            )
            user_context = f"{user_context}\nCustomer status: {status}".strip()

        if intent == "service_request" and any(w in message.lower() for w in ("book", "appointment", "reserve", "slot")):
            user_context = (
                f"{user_context}\nBooking intent detected — collect date, time, and service, "
                "then use bookAppointment or listAvailableSlots tools."
            ).strip()

        if lead_context:
            user_context = f"{user_context}\nLead score: {lead_context}".strip()

        media_note = ""
        if saved_files:
            media_note = f"Customer uploaded {len(saved_files)} file(s): {', '.join(saved_files)}."

        system_prompt = build_system_prompt(profile, localized_system_prompt_addendum(lang))
        tool_addendum = (
            "\n\nWhen the customer wants to book, reschedule, get a quote, or pay, "
            "use the available tools (listAvailableSlots, bookAppointment, qualifyLead, createPaymentLink)."
        )
        user_content = build_agent_user_content(
            message,
            internal_context,
            web_context,
            user_context,
            media_note,
        )

        t2 = time.perf_counter()
        reply = ""
        appointment_note = ""

        if openai_tool_calling_available() and intent in ("service_request", "general"):

            def _tool_invoke(name: str, args: dict) -> str:
                merged = {**args, "user_id": user_id}
                result = tools.invoke(
                    name,
                    merged,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
                if name == "bookAppointment" and '"ok": true' in result.lower():
                    nonlocal appointment_note
                    appointment_note = result[:400]
                return result

            reply, _traces = generate_with_tools(
                system_prompt=system_prompt + tool_addendum,
                user_content=user_content,
                history=history,
                tool_invoke=_tool_invoke,
            )

        if not reply:
            heuristic = self._heuristic_tool_notes(
                message,
                tools,
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=correlation_id,
            )
            if heuristic:
                user_context = f"{user_context}\n\nTool results:\n{heuristic}".strip()
                if '"ok": true' in heuristic.lower() and "bookAppointment" in heuristic:
                    appointment_note = heuristic[:400]
            reply = generate_response(
                user_message=message,
                internal_context=internal_context,
                web_context=web_context,
                history=history,
                user_context=user_context,
                media_note=media_note,
                system_prompt=system_prompt,
            )
        logger.info("%sLLM reply: %.1fs", log_prefix, time.perf_counter() - t2)

        response_ms = (time.perf_counter() - t0) * 1000
        record_message(
            tenant_id,
            user_id,
            "outbound",
            intent=intent,
            response_ms=response_ms,
            message_preview=reply[:200],
        )

        self._notify_owner_live(
            tenant_id=tenant_id,
            profile=profile,
            message=message,
            reply=reply,
            intent=intent,
            appointment_note=appointment_note,
        )

        personal = self.data_store.get_personal_data(scoped)
        if personal and "retention" not in reply.lower():
            if not any("retention" in turn.get("content", "").lower() for turn in history if turn.get("role") == "assistant"):
                reply += f"\n\n_{self.data_store.retention_notice()}_"

        reply += t("disclaimer", lang)
        reply += t("feedback_prompt", lang)

        if expired_note:
            reply = expired_note + reply

        self.memory.add_turn(user_id, message, reply, tenant_id)
        if correlation_id:
            set_pending_feedback(user_id, correlation_id)
        return reply

