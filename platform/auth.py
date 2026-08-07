"""RBAC/ABAC and service auth (WC-19, WC-20, WC-21, WC-23, WC-24, WC-25, WC-41)."""

from __future__ import annotations

import os
from functools import wraps
from typing import Callable

from flask import has_request_context, redirect, request, session, url_for

from config import ADMIN_API_KEY as CONFIG_ADMIN_API_KEY

ROLES = {"admin", "operator", "agent", "readonly"}
DEFAULT_ROLE = "agent"

ADMIN_API_KEY = CONFIG_ADMIN_API_KEY or os.getenv("ADMIN_API_KEY", "")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
REQUIRE_MFA_HEADER = os.getenv("REQUIRE_MFA_HEADER", "0") == "1"


def admin_configured() -> bool:
    return bool(ADMIN_API_KEY)


def is_admin_authenticated() -> bool:
    if not ADMIN_API_KEY:
        return False
    if request.headers.get("X-Admin-Key", "") == ADMIN_API_KEY:
        return True
    return session.get("admin_authenticated") is True


def render_admin_not_configured():
    from flask import render_template_string

    return render_template_string(
        """
        <!DOCTYPE html><html><body style="font-family:system-ui;max-width:520px;margin:4rem auto;padding:1rem">
        <h1>Admin not configured</h1>
        <p>Add to your <code>.env</code> file:</p>
        <pre style="background:#f4f4f5;padding:1rem;border-radius:8px">ADMIN_API_KEY=your-secret-key-here</pre>
        <p>Restart <code>python app.py</code>, then open <a href="/admin/login">/admin/login</a>.</p>
        </body></html>
        """
    )


def require_admin_api_key(view: Callable):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not ADMIN_API_KEY:
            return {"error": "Admin API not configured — set ADMIN_API_KEY in .env"}, 503
        if not is_admin_authenticated():
            return {"error": "Unauthorized"}, 401
        if REQUIRE_MFA_HEADER and request.headers.get("X-MFA-Verified") != "true":
            return {"error": "MFA required"}, 403
        return view(*args, **kwargs)

    return wrapper


def require_admin_browser(view: Callable):
    """Admin HTML routes — redirect to login when not authenticated."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not ADMIN_API_KEY:
            return render_admin_not_configured(), 503
        if not is_admin_authenticated():
            return redirect(url_for("admin_login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapper


def get_request_role() -> str:
    if not has_request_context():
        return DEFAULT_ROLE
    return request.headers.get("X-Role", DEFAULT_ROLE)


def get_request_tenant() -> str:
    if not has_request_context():
        return os.getenv("DEFAULT_TENANT_ID", "default")
    return request.headers.get("X-Tenant-Id", os.getenv("DEFAULT_TENANT_ID", "default"))


def get_request_region() -> str:
    if not has_request_context():
        return os.getenv("DEFAULT_REGION", "eu")
    return request.headers.get("X-Region", os.getenv("DEFAULT_REGION", "eu"))


def authorize(action: str, resource: str) -> bool:
    """ABAC: tenant + region + role."""
    role = get_request_role()
    if role == "admin":
        return True
    if action == "read" and role in ("operator", "agent", "readonly"):
        return True
    if action == "write" and role in ("operator", "agent"):
        return True
    if action == "tool" and role == "agent":
        return True
    return False


def validate_service_token(token: str) -> bool:
    return bool(SERVICE_API_KEY and token == SERVICE_API_KEY)
