"""Public signup, demo requests, and setup tokens for landing page CTAs."""

from __future__ import annotations

import re
import secrets
import sqlite3
import time

from config import BASE_DIR, WEBHOOK_BASE_URL
from platform.business_profile import BusinessProfile, load_business_profile, save_business_profile
from platform.business_profile import _profile_path

ONBOARDING_DB = BASE_DIR / ".user_data" / "onboarding.db"
TOKEN_TTL_SECONDS = 7 * 86400


def _connect() -> sqlite3.Connection:
    ONBOARDING_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ONBOARDING_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS setup_tokens (
                tenant_id TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                email TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS demo_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                business_name TEXT DEFAULT '',
                message TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            """
        )


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:36] or "business"


def _unique_tenant_id(base: str) -> str:
    candidate = base
    n = 0
    while _profile_path(candidate).exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def issue_setup_token(tenant_id: str, email: str) -> str:
    _init_db()
    token = secrets.token_urlsafe(32)
    expires = time.time() + TOKEN_TTL_SECONDS
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO setup_tokens (tenant_id, token, email, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id) DO UPDATE SET
                token = excluded.token,
                email = excluded.email,
                expires_at = excluded.expires_at
            """,
            (tenant_id, token, email, expires, time.time()),
        )
    return token


def verify_setup_token(tenant_id: str, token: str) -> bool:
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT token, expires_at FROM setup_tokens WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    if not row or row["token"] != token:
        return False
    return time.time() < row["expires_at"]


def get_setup_email(tenant_id: str) -> str:
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT email FROM setup_tokens WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    return row["email"] if row else ""


def setup_url(tenant_id: str, token: str) -> str:
    base = (WEBHOOK_BASE_URL or "http://localhost:5000").rstrip("/")
    return f"{base}/setup?tenant={tenant_id}&token={token}"


def infer_industry_from_specialization(specialization: str) -> str:
    """Map free-text specialization to internal industry slug for demo/web search."""
    s = specialization.lower()
    keywords = {
        "restaurant": [
            "restaurant", "café", "cafe", "eetcafe", "bistro", "pizzeria", "horeca",
            "bakker", "catering", "trattoria", "steakhouse", "sushi",
        ],
        "salon": [
            "kapsalon", "salon", "kapper", "nagel", "beauty", "barber", "haar",
            "wellness", "spa", "massage", "nagels",
        ],
        "retail": [
            "winkel", "shop", "retail", "kleding", "mode", "supermarkt", "boutique",
            "fietsen", "meubel", "electro",
        ],
        "healthcare": [
            "tandarts", "fysio", "kliniek", "zorg", "huisarts", "therapie", "diëtist",
        ],
        "energy": [
            "zonnepanel", "solar", "energie", "warmtepomp", "elektricien", "installateur",
            "pv", "thuisbatterij", "laadpaal", "hvac", "airco", "verwarming",
        ],
    }
    for industry, words in keywords.items():
        if any(w in s for w in words):
            return industry
    return "services"


def create_business_signup(
    *,
    business_name: str,
    email: str = "",
    business_city: str = "",
    specialization: str = "",
    industry: str = "",
    tier: str = "starter",
) -> dict:
    """Create tenant from landing page signup."""
    _init_db()
    if not business_name.strip():
        raise ValueError("business_name is required")
    if not business_city.strip():
        raise ValueError("business_city is required")
    if not specialization.strip():
        raise ValueError("specialization is required")

    tenant_id = _unique_tenant_id(slugify(business_name))
    spec = specialization.strip()
    resolved_industry = (industry.strip() or infer_industry_from_specialization(spec) or "general")
    contact_email = email.strip().lower() or f"{tenant_id}@pending.local"

    profile = BusinessProfile(
        tenant_id=tenant_id,
        business_name=business_name.strip(),
        business_city=business_city.strip(),
        specialization=spec,
        industry=resolved_industry,
        tagline=f"WhatsApp assistant for {business_name.strip()}",
        welcome_message=(
            f"Hi! Welcome to {business_name.strip()}.\n\n"
            "How can I help you today — booking, pricing, hours, or a question?"
        ),
        docs_subdir=tenant_id,
        subscription_tier=tier if tier in ("starter", "growth", "enterprise", "free") else "starter",
    )
    save_business_profile(profile)

    docs_dir = BASE_DIR / "docs" / tenant_id
    docs_dir.mkdir(parents=True, exist_ok=True)
    readme = docs_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# {business_name}\n\nSpecialization: {spec}\n\nAdd your business docs here.\n",
            encoding="utf-8",
        )

    from platform.industry_faqs import write_industry_seed_docs

    write_industry_seed_docs(
        docs_dir,
        business_name=business_name.strip(),
        industry=resolved_industry,
        specialization=spec,
        business_city=business_city.strip(),
    )

    token = issue_setup_token(tenant_id, contact_email)
    return {
        "tenant_id": tenant_id,
        "business_name": profile.business_name,
        "tier": profile.subscription_tier,
        "setup_token": token,
        "setup_url": setup_url(tenant_id, token),
    }


def record_demo_request(*, name: str, email: str, business_name: str = "", message: str = "") -> int:
    _init_db()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO demo_requests (name, email, business_name, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name.strip(), email.strip().lower(), business_name.strip(), message.strip(), time.time()),
        )
        return int(cur.lastrowid)
