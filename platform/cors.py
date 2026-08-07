"""CORS for landing page → backend public API."""

from __future__ import annotations

from flask import request

from config import IS_PRODUCTION, LANDING_ALLOWED_ORIGINS


def _allowed_origin() -> str | None:
    origin = request.headers.get("Origin", "")
    if not origin:
        return "*"
    if origin in LANDING_ALLOWED_ORIGINS:
        return origin
    if not IS_PRODUCTION and ("localhost" in origin or "127.0.0.1" in origin):
        return origin
    return None


def apply_cors(response):
    if not request.path.startswith("/public/") and not request.path.startswith("/onboard/"):
        return response
    origin = _allowed_origin()
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, ngrok-skip-browser-warning"
        response.headers["Vary"] = "Origin"
    return response


def handle_preflight():
    if request.method == "OPTIONS" and (
        request.path.startswith("/public/") or request.path.startswith("/onboard/")
    ):
        from flask import make_response

        resp = make_response("", 204)
        return apply_cors(resp)
