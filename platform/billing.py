"""Stripe subscription billing — tenant-scoped, aligned with AppAssist tiers."""

from __future__ import annotations

import logging

import stripe

from config import (
    RETENTION_TIERS,
    STRIPE_PRICE_GROWTH,
    STRIPE_PRICE_PREMIUM,
    STRIPE_PRICE_STANDARD,
    STRIPE_PRICE_STARTER,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
)
from platform.business_profile import BusinessProfile, load_business_profile, save_business_profile

logger = logging.getLogger(__name__)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

TIER_PRICES = {
    "starter": STRIPE_PRICE_STARTER or STRIPE_PRICE_STANDARD,
    "growth": STRIPE_PRICE_GROWTH or STRIPE_PRICE_PREMIUM,
    "standard": STRIPE_PRICE_STARTER or STRIPE_PRICE_STANDARD,
    "premium": STRIPE_PRICE_GROWTH or STRIPE_PRICE_PREMIUM,
}

TIER_RETENTION = {
    "free": RETENTION_TIERS.get("free", 12),
    "starter": RETENTION_TIERS.get("standard", 168),
    "growth": RETENTION_TIERS.get("premium", 720),
    "enterprise": RETENTION_TIERS.get("premium", 720),
    "standard": RETENTION_TIERS.get("standard", 168),
    "premium": RETENTION_TIERS.get("premium", 720),
}


def billing_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY)


def create_checkout_session(
    user_id: str,
    tier: str = "starter",
    success_url: str = "",
    cancel_url: str = "",
    tenant_id: str = "",
) -> str | None:
    if not billing_enabled():
        return None

    price_id = TIER_PRICES.get(tier, TIER_PRICES.get("starter", ""))
    if not price_id:
        logger.error("No Stripe price configured for tier=%s", tier)
        return None

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url or "https://example.com/billing/success",
        cancel_url=cancel_url or "https://example.com/billing/cancel",
        metadata={"user_id": user_id, "tier": tier, "tenant_id": tenant_id},
    )
    return session.url


def _apply_tenant_tier(tenant_id: str, tier: str) -> None:
    if not tenant_id:
        return
    profile = load_business_profile(tenant_id)
    profile.subscription_tier = tier
    save_business_profile(profile)


def handle_webhook(payload: bytes, sig_header: str, data_store_factory) -> dict:
    if not STRIPE_WEBHOOK_SECRET:
        return {"error": "webhook secret not configured"}

    event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata", {})
        user_id = meta.get("user_id", "")
        tier = meta.get("tier", "starter")
        tenant_id = meta.get("tenant_id", "")
        customer_id = session.get("customer", "")
        sub_id = session.get("subscription", "")

        if tenant_id:
            _apply_tenant_tier(tenant_id, tier)

        if user_id:
            from config import DEFAULT_TENANT_ID
            from user_data import _storage_key

            store = data_store_factory()
            scoped = _storage_key(user_id, tenant_id or DEFAULT_TENANT_ID)
            if hasattr(store, "set_subscription"):
                store.set_subscription(scoped, tier, customer_id, sub_id, "active")
                hours = TIER_RETENTION.get(tier, TIER_RETENTION["starter"])
                if hasattr(store, "set_retention_hours"):
                    store.set_retention_hours(hours)

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        meta = sub.get("metadata", {})
        tenant_id = meta.get("tenant_id", "")
        if tenant_id:
            _apply_tenant_tier(tenant_id, "free")
        logger.info("Subscription cancelled: %s tenant=%s", sub.get("id"), tenant_id)

    elif event["type"] == "invoice.payment_succeeded":
        logger.info("Payment succeeded: %s", event["data"]["object"].get("id"))

    return {"status": "ok"}


def get_tier_for_user(store, scoped_user_id: str) -> str:
    if hasattr(store, "get_subscription_tier"):
        return store.get_subscription_tier(scoped_user_id)
    return "free"
