"""IoT webhook stub (WC-46)."""

from __future__ import annotations

from platform.auth import validate_service_token
from platform.observability import log_structured


def handle_iot_payload(payload: dict, auth_token: str) -> tuple[dict, int]:
    if not validate_service_token(auth_token):
        return {"error": "Unauthorized"}, 401
    log_structured("iot_event", device_id=payload.get("device_id", ""), event=payload.get("event", ""))
    return {"status": "accepted"}, 202
