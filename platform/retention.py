"""Subscription-tier data retention."""

from __future__ import annotations

from config import DATA_RETENTION_HOURS, RETENTION_TIERS


def retention_hours_for_tier(tier: str) -> int:
    return RETENTION_TIERS.get(tier, DATA_RETENTION_HOURS)


def apply_retention_to_store(store, scoped_user_id: str) -> None:
    tier = "free"
    if hasattr(store, "get_subscription_tier"):
        tier = store.get_subscription_tier(scoped_user_id)
    hours = retention_hours_for_tier(tier)
    if hasattr(store, "set_retention_hours"):
        store.set_retention_hours(hours)
