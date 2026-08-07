"""Per-tenant rate limiting with Redis (distributed) or in-memory fallback."""

from __future__ import annotations

import time
from collections import defaultdict

from platform.redis_client import get_redis, redis_available

WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 30
_tool_calls: dict[str, list[float]] = defaultdict(list)
_ingress_calls: dict[str, list[float]] = defaultdict(list)
_public_calls: dict[str, list[float]] = defaultdict(list)


def _redis_allow(key: str, limit: int, window: int = WINDOW_SECONDS) -> bool:
    r = get_redis()
    if not r:
        return True
    pipe = r.pipeline()
    now = time.time()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window + 1)
    _, _, count, _ = pipe.execute()
    return count <= limit


def _memory_prune(key: str, store: dict[str, list[float]]) -> list[float]:
    now = time.time()
    store[key] = [t for t in store[key] if now - t < WINDOW_SECONDS]
    return store[key]


def allow_ingress(tenant_id: str, user_id: str) -> bool:
    key = f"rl:ingress:{tenant_id}:{user_id}"
    if redis_available():
        return _redis_allow(key, MAX_REQUESTS_PER_WINDOW)
    hits = _memory_prune(key, _ingress_calls)
    if len(hits) >= MAX_REQUESTS_PER_WINDOW:
        return False
    _ingress_calls[key].append(time.time())
    return True


def allow_tool(tenant_id: str, tool_name: str) -> bool:
    key = f"rl:tool:{tenant_id}:{tool_name}"
    if redis_available():
        return _redis_allow(key, 20)
    hits = _memory_prune(key, _tool_calls)
    if len(hits) >= 20:
        return False
    _tool_calls[key].append(time.time())
    return True


def allow_public(client_ip: str, limit: int = 10, window: int = 3600) -> bool:
    """Rate limit public landing-page API (signups, demos) per IP."""
    key = f"rl:public:{client_ip or 'unknown'}"
    if redis_available():
        return _redis_allow(key, limit, window)
    now = time.time()
    _public_calls[key] = [t for t in _public_calls[key] if now - t < window]
    if len(_public_calls[key]) >= limit:
        return False
    _public_calls[key].append(now)
    return True
