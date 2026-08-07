"""Async event bus stub (WC-56)."""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable

_event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
_handlers: list[Callable[[dict[str, Any]], None]] = []
_worker_started = False


def subscribe(handler: Callable[[dict[str, Any]], None]) -> None:
    _handlers.append(handler)


def publish(event_type: str, payload: dict[str, Any]) -> None:
    _event_queue.put({"type": event_type, **payload})


def _worker() -> None:
    while True:
        evt = _event_queue.get()
        for handler in _handlers:
            try:
                handler(evt)
            except Exception:
                pass


def start_event_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    threading.Thread(target=_worker, daemon=True).start()
    _worker_started = True
