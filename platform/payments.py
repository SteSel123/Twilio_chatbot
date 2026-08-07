"""Stripe payment links for proactive WhatsApp payments."""

from __future__ import annotations

import logging

import stripe

from config import STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def payments_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY)


def create_payment_link(
    *,
    amount_cents: int,
    currency: str = "eur",
    description: str,
    tenant_id: str,
    user_id: str,
    metadata: dict | None = None,
) -> str | None:
    """Create a Stripe Payment Link and return the URL."""
    if not payments_enabled():
        logger.warning("Stripe not configured — cannot create payment link")
        return None

    meta = {"tenant_id": tenant_id, "user_id": user_id, **(metadata or {})}
    try:
        product = stripe.Product.create(name=description[:120])
        price = stripe.Price.create(
            product=product.id,
            unit_amount=amount_cents,
            currency=currency.lower(),
        )
        link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            metadata=meta,
            after_completion={"type": "hosted_confirmation", "hosted_confirmation": {"custom_message": "Thank you!"}},
        )
        return link.url
    except Exception as exc:
        logger.error("Payment link creation failed: %s", exc)
        return None
