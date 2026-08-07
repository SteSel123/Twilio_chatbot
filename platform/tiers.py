"""Subscription tier limits — aligned with AppAssist landing pricing."""

from __future__ import annotations

from platform.analytics import get_monthly_conversations
from platform.business_profile import load_business_profile

TIER_LIMITS: dict[str, dict] = {
    "free": {
        "conversations_per_month": 50,
        "phone_numbers": 1,
        "voice_images": False,
        "web_search": True,
        "label": "Trial",
    },
    "starter": {
        "conversations_per_month": 400,
        "phone_numbers": 1,
        "voice_images": False,
        "web_search": True,
        "label": "Starter",
    },
    "growth": {
        "conversations_per_month": None,
        "phone_numbers": 3,
        "voice_images": True,
        "web_search": True,
        "label": "Growth",
    },
    "enterprise": {
        "conversations_per_month": None,
        "phone_numbers": 10,
        "voice_images": True,
        "web_search": True,
        "label": "Enterprise",
    },
    # Legacy aliases
    "standard": {
        "conversations_per_month": 400,
        "phone_numbers": 1,
        "voice_images": False,
        "web_search": True,
        "label": "Starter",
    },
    "premium": {
        "conversations_per_month": None,
        "phone_numbers": 3,
        "voice_images": True,
        "web_search": True,
        "label": "Growth",
    },
}


def get_tenant_tier(tenant_id: str) -> str:
    profile = load_business_profile(tenant_id)
    return getattr(profile, "subscription_tier", None) or "starter"


def tier_config(tenant_id: str) -> dict:
    tier = get_tenant_tier(tenant_id)
    return TIER_LIMITS.get(tier, TIER_LIMITS["starter"])


def check_conversation_allowed(tenant_id: str) -> tuple[bool, str]:
    cfg = tier_config(tenant_id)
    limit = cfg.get("conversations_per_month")
    if limit is None:
        return True, ""
    used = get_monthly_conversations(tenant_id)
    if used >= limit:
        return False, (
            f"Monthly conversation limit reached ({used}/{limit}). "
            f"Upgrade to Growth for unlimited conversations."
        )
    return True, ""


def tier_allows_media(tenant_id: str) -> bool:
    return bool(tier_config(tenant_id).get("voice_images"))


def tier_allows_web_search(tenant_id: str) -> bool:
    return bool(tier_config(tenant_id).get("web_search"))
