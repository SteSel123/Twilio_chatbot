"""Shared Redis connection."""

from __future__ import annotations

import logging

import redis

from config import REDIS_URL

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
_available: bool | None = None


def get_redis() -> redis.Redis | None:
    global _client, _available
    if _available is False:
        return None
    if _client is None:
        try:
            _client = redis.from_url(REDIS_URL, decode_responses=True)
            _client.ping()
            _available = True
        except Exception as exc:
            logger.warning("Redis unavailable: %s", exc)
            _available = False
            _client = None
    return _client


def redis_available() -> bool:
    return get_redis() is not None
