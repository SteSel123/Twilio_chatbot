"""Reply quality feedback collection."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

FEEDBACK_PENDING_KEY = "feedback_pending:{user_id}"


def is_feedback_response(message: str) -> int | None:
    stripped = message.strip()
    if stripped in ("1", "👍"):
        return 1
    if stripped in ("2", "👎"):
        return 0
    return None


def set_pending_feedback(user_id: str, correlation_id: str) -> None:
    from platform.redis_client import get_redis, redis_available

    r = get_redis()
    if redis_available() and r:
        r.setex(FEEDBACK_PENDING_KEY.format(user_id=user_id), 3600, correlation_id)


def get_pending_feedback(user_id: str) -> str | None:
    from platform.redis_client import get_redis, redis_available

    r = get_redis()
    if redis_available() and r:
        return r.get(FEEDBACK_PENDING_KEY.format(user_id=user_id))
    return None


def clear_pending_feedback(user_id: str) -> None:
    from platform.redis_client import get_redis, redis_available

    r = get_redis()
    if redis_available() and r:
        r.delete(FEEDBACK_PENDING_KEY.format(user_id=user_id))


def record_feedback(store, scoped_user_id: str, rating: int, correlation_id: str = "") -> None:
    if hasattr(store, "record_feedback"):
        store.record_feedback(scoped_user_id, rating, correlation_id)
    logger.info("Feedback recorded: user=%s rating=%d", scoped_user_id, rating)
