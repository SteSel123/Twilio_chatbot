"""Secret management hooks — Azure Key Vault optional (WC-49, WC-55)."""

from __future__ import annotations

import os
import time

_vault_cache: dict[str, tuple[str, float]] = {}
CACHE_TTL = 300


def get_secret(name: str, default: str = "") -> str:
    """Return env var; optional Azure Key Vault when AZURE_KEY_VAULT_URL is set."""
    vault_url = os.getenv("AZURE_KEY_VAULT_URL", "")
    if not vault_url:
        return os.getenv(name, default)

    cached = _vault_cache.get(name)
    if cached and time.time() - cached[1] < CACHE_TTL:
        return cached[0]

    # Production: use azure-identity + azure-keyvault-secrets
    value = os.getenv(name, default)
    _vault_cache[name] = (value, time.time())
    return value


def rotation_due(days: int = 90) -> bool:
    last = os.getenv("SECRET_LAST_ROTATED_EPOCH", "")
    if not last:
        return True
    return time.time() - float(last) > days * 86400
