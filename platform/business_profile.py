"""Per-tenant business profile configuration for SMB WhatsApp assistant."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config import BASE_DIR, DEFAULT_TENANT_ID

logger = logging.getLogger(__name__)

BUSINESSES_DIR = BASE_DIR / "businesses"
DEFAULT_DOCS_DIR = BASE_DIR / "docs"

DEFAULT_TOOLS = ("searchBusinessDocs", "getCustomerContext", "webSearch")


@dataclass
class ExternalMcpServer:
    label: str
    url: str
    transport: str = "streamable-http"
    description: str = ""
    bearer_token_env: str = ""
    bearer_token: str = ""


@dataclass
class BusinessProfile:
    tenant_id: str = DEFAULT_TENANT_ID
    business_name: str = "Your Business"
    business_city: str = ""
    specialization: str = ""
    industry: str = "general"
    tagline: str = "Your friendly WhatsApp assistant"
    welcome_message: str = (
        "Hi! I'm here to help you.\n\n"
        "Tell me what you need — booking, pricing, hours, or a question about our services."
    )
    system_prompt_extra: str = ""
    enabled_tools: list[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    docs_subdir: str = "default"
    language_default: str = "en"
    handoff_phrase: str = "speak to human"
    web_search_hint: str = "business services pricing hours location"
    external_mcp_servers: list[dict] = field(default_factory=list)
    subscription_tier: str = "starter"
    twilio_whatsapp_from: str = ""
    google_calendar_id: str = "primary"
    review_url: str = ""
    handoff_slack_webhook: str = ""

    @property
    def docs_dir(self) -> Path:
        tenant_docs = BASE_DIR / "docs" / self.docs_subdir
        if tenant_docs.exists():
            return tenant_docs
        return DEFAULT_DOCS_DIR

    def to_dict(self) -> dict:
        return asdict(self)


def _profile_path(tenant_id: str) -> Path:
    return BUSINESSES_DIR / f"{tenant_id}.json"


def default_profile(tenant_id: str = DEFAULT_TENANT_ID) -> BusinessProfile:
    return BusinessProfile(tenant_id=tenant_id)


def load_business_profile(tenant_id: str = DEFAULT_TENANT_ID) -> BusinessProfile:
    """Load profile from businesses/{tenant_id}.json or return defaults."""
    BUSINESSES_DIR.mkdir(parents=True, exist_ok=True)
    path = _profile_path(tenant_id)
    if not path.exists():
        if tenant_id != DEFAULT_TENANT_ID:
            return load_business_profile(DEFAULT_TENANT_ID)
        seed = BUSINESSES_DIR / "default.json"
        if seed.exists():
            path = seed
        else:
            return default_profile(tenant_id)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tenant_id"] = tenant_id
        return BusinessProfile(**{k: v for k, v in data.items() if k in BusinessProfile.__dataclass_fields__})
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to load business profile for %s: %s", tenant_id, exc)
        return default_profile(tenant_id)


def save_business_profile(profile: BusinessProfile) -> None:
    BUSINESSES_DIR.mkdir(parents=True, exist_ok=True)
    data = profile.to_dict()
    data.pop("tenant_id", None)
    _profile_path(profile.tenant_id).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_business_profiles() -> list[str]:
    BUSINESSES_DIR.mkdir(parents=True, exist_ok=True)
    ids = [p.stem for p in BUSINESSES_DIR.glob("*.json")]
    return sorted(set(ids))


def _normalize_whatsapp_number(value: str) -> str:
    return (value or "").strip().lower().replace("whatsapp:", "")


def find_tenant_by_whatsapp_number(to_number: str) -> str | None:
    """Map inbound Twilio To number to tenant_id via profile.twilio_whatsapp_from."""
    target = _normalize_whatsapp_number(to_number)
    if not target:
        return None
    for tenant_id in list_business_profiles():
        profile = load_business_profile(tenant_id)
        configured = _normalize_whatsapp_number(profile.twilio_whatsapp_from)
        if configured and configured == target:
            return tenant_id
    return None


def whatsapp_from_for_tenant(tenant_id: str, fallback: str = "") -> str:
    profile = load_business_profile(tenant_id)
    if profile.twilio_whatsapp_from:
        return profile.twilio_whatsapp_from
    return fallback
