"""Tenant isolation, retention, residency (WC-22, WC-31, WC-47, WC-50, WC-59)."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_REGION = os.getenv("DEFAULT_REGION", "eu")
TENANT_REGIONS: dict[str, str] = {
    "default": DEFAULT_REGION,
}


@dataclass
class TenantContext:
    tenant_id: str
    region: str


def resolve_tenant(
    tenant_id: str | None = None,
    header_tenant: str | None = None,
    twilio_to: str | None = None,
) -> TenantContext:
    tid = header_tenant or tenant_id or os.getenv("DEFAULT_TENANT_ID", "default")
    if twilio_to:
        from platform.business_profile import find_tenant_by_whatsapp_number

        mapped = find_tenant_by_whatsapp_number(twilio_to)
        if mapped:
            tid = mapped
    region = TENANT_REGIONS.get(tid, DEFAULT_REGION)
    return TenantContext(tenant_id=tid, region=region)


def tenant_storage_prefix(tenant_id: str) -> str:
    return f"tenant:{tenant_id}"


def enforce_data_residency(region: str, allowed_regions: set[str] | None = None) -> bool:
    allowed = allowed_regions or {DEFAULT_REGION}
    return region in allowed
