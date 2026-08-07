"""GDPR export and erasure (WC-62)."""

from __future__ import annotations

import json

from memory import ConversationMemory
from storage import get_data_store
from user_data import _storage_key


def export_user_data(user_id: str, tenant_id: str) -> dict:
    store = get_data_store()
    memory = ConversationMemory()
    scoped = _storage_key(user_id, tenant_id)
    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "case_state": store.get_case_state(scoped),
        "personal_data": store.get_personal_data(scoped),
        "conversation": memory.get_history(user_id, tenant_id),
    }


def erase_user_data(user_id: str, tenant_id: str) -> None:
    store = get_data_store()
    memory = ConversationMemory()
    scoped = _storage_key(user_id, tenant_id)
    store.clear_user(scoped)
    memory.clear(user_id, tenant_id)
