"""Redis job queue for inbound message processing."""

from __future__ import annotations

import logging
from typing import Callable

from config import USE_REDIS_QUEUE
from platform.redis_client import get_redis, redis_available

logger = logging.getLogger(__name__)

_queue = None


def _get_queue():
    global _queue
    if _queue is None and redis_available():
        from rq import Queue

        _queue = Queue("whatsapp", connection=get_redis(), default_timeout=180)
    return _queue


def enqueue_message_processing(
    form: dict[str, str],
    tenant_id: str,
    *,
    inline_fn: Callable[[], None] | None = None,
) -> bool:
    """Enqueue message job. Falls back to inline thread when Redis unavailable."""
    if USE_REDIS_QUEUE and redis_available():
        from worker import process_message_job

        q = _get_queue()
        if q:
            q.enqueue(process_message_job, form, tenant_id, job_timeout=180)
            logger.info("Enqueued message job for tenant=%s", tenant_id)
            return True

    if inline_fn:
        import threading

        threading.Thread(target=inline_fn, daemon=True).start()
        return True
    return False
