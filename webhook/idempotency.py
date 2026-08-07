"""MessageSid idempotency — Redis-backed with in-memory fallback."""

from __future__ import annotations

import time

from platform.redis_client import get_redis, redis_available

TTL_SECONDS = 3600
_processed_sids: dict[str, float] = {}


def is_duplicate(message_sid: str) -> bool:
    if not message_sid:
        return False

    r = get_redis()
    if redis_available() and r:
        key = f"idem:{message_sid}"
        if r.exists(key):
            return True
        r.setex(key, TTL_SECONDS, "1")
        return False

    now = time.time()
    expired = [sid for sid, ts in _processed_sids.items() if now - ts > TTL_SECONDS]
    for sid in expired:
        del _processed_sids[sid]

    if message_sid in _processed_sids:
        return True

    _processed_sids[message_sid] = now
    return False
