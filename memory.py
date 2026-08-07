"""Short-term per-user conversation memory — Redis or file fallback."""

from __future__ import annotations

import json
from pathlib import Path

from config import DEFAULT_TENANT_ID, MAX_HISTORY_TURNS, MEMORY_DIR
from platform.redis_client import get_redis, redis_available


class ConversationMemory:
    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or MEMORY_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _redis_key(self, user_id: str, tenant_id: str) -> str:
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        return f"mem:{tenant_id}:{safe_id}"

    def _path(self, user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> Path:
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        tenant_dir = self.storage_dir / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir / f"{safe_id}.json"

    def get_history(self, user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> list[dict[str, str]]:
        r = get_redis()
        if redis_available() and r:
            raw = r.get(self._redis_key(user_id, tenant_id))
            if raw:
                try:
                    data = json.loads(raw)
                    return data if isinstance(data, list) else []
                except json.JSONDecodeError:
                    return []

        path = self._path(user_id, tenant_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def add_turn(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        history = self.get_history(user_id, tenant_id)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_message})
        max_messages = MAX_HISTORY_TURNS * 2
        if len(history) > max_messages:
            history = history[-max_messages:]

        payload = json.dumps(history, ensure_ascii=False)
        r = get_redis()
        if redis_available() and r:
            r.setex(self._redis_key(user_id, tenant_id), 86400 * 7, payload)
            return

        self._path(user_id, tenant_id).write_text(payload, encoding="utf-8")

    def clear(self, user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> None:
        r = get_redis()
        if redis_available() and r:
            r.delete(self._redis_key(user_id, tenant_id))
        path = self._path(user_id, tenant_id)
        if path.exists():
            path.unlink()
