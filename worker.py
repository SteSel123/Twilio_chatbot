"""RQ worker — message processing and proactive outbound scheduler."""

from __future__ import annotations

import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def process_message_job(form: dict[str, str], tenant_id: str) -> None:
    """Process inbound WhatsApp message (called by RQ worker)."""
    from agent import BusinessAgent
    from webhook.handler import _process_and_reply
    from webhook.handler import _sanitize_message
    from schemas.normalized_message import from_twilio_form

    agent = BusinessAgent()
    msg = _sanitize_message(from_twilio_form(form))
    _process_and_reply(msg, agent.handle_message, tenant_id)


def process_outbound_job() -> int:
    """Process due proactive outbound messages."""
    from platform.outbound import process_due_messages

    return process_due_messages()


if __name__ == "__main__":
    from redis import Redis
    from rq import Worker

    from config import REDIS_URL

    conn = Redis.from_url(REDIS_URL)
    worker = Worker(["whatsapp", "outbound"], connection=conn)
    logger.info("Starting RQ worker on queues 'whatsapp' and 'outbound'")

    import threading

    def _outbound_loop():
        while True:
            try:
                n = process_outbound_job()
                if n:
                    logger.info("Sent %d outbound message(s)", n)
            except Exception:
                logger.exception("Outbound scheduler error")
            time.sleep(60)

    threading.Thread(target=_outbound_loop, daemon=True).start()
    worker.work()
