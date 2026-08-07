"""PostgreSQL-backed user data store (production)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

from config import DATA_RETENTION_HOURS, DATABASE_URL, UPLOADS_DIR
from patterns import COUNTRY_PATTERN, PROCESS_PATTERN
from user_data import (
    EMAIL_PATTERN,
    FORM_FIELDS,
    KEY_VALUE_PATTERN,
    PERSONAL_FIELD_ALIASES,
    PHONE_PATTERN,
    UserDataStore,
    _safe_id,
)


class PostgresUserDataStore(UserDataStore):
    """Same interface as UserDataStore but backed by PostgreSQL."""

    def __init__(self, dsn: str | None = None, retention_hours: int | None = None):
        self.dsn = dsn or DATABASE_URL
        self._retention_hours = retention_hours or DATA_RETENTION_HOURS
        self._init_db()

    def _connect(self):
        return psycopg2.connect(self.dsn)

    def _init_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        subscription_tier TEXT DEFAULT 'free'
                    );
                    CREATE TABLE IF NOT EXISTS personal_data (
                        user_id TEXT NOT NULL,
                        field_name TEXT NOT NULL,
                        field_value TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (user_id, field_name)
                    );
                    CREATE TABLE IF NOT EXISTS case_state (
                        user_id TEXT PRIMARY KEY,
                        country TEXT DEFAULT '',
                        visa_type TEXT DEFAULT '',
                        process_name TEXT DEFAULT '',
                        documents_provided TEXT DEFAULT '[]',
                        missing_documents TEXT DEFAULT '[]',
                        next_steps TEXT DEFAULT '[]',
                        updated_at TIMESTAMPTZ NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS uploaded_files (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        media_type TEXT DEFAULT '',
                        uploaded_at TIMESTAMPTZ NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS user_consent (
                        user_id TEXT PRIMARY KEY,
                        consented_at TIMESTAMPTZ NOT NULL,
                        privacy_version TEXT DEFAULT '1.0'
                    );
                    CREATE TABLE IF NOT EXISTS reply_feedback (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        correlation_id TEXT,
                        rating INTEGER NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        user_id TEXT PRIMARY KEY,
                        stripe_customer_id TEXT,
                        stripe_subscription_id TEXT,
                        tier TEXT DEFAULT 'free',
                        status TEXT DEFAULT 'inactive',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
            conn.commit()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _expires_at(self, hours: int | None = None) -> datetime:
        h = hours if hours is not None else self._retention_hours
        return self._now() + timedelta(hours=h)

    def set_retention_hours(self, hours: int) -> None:
        self._retention_hours = hours

    def get_subscription_tier(self, user_id: str) -> str:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tier FROM subscriptions WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
        return row[0] if row else "free"

    def set_subscription(self, user_id: str, tier: str, stripe_customer_id: str = "", stripe_sub_id: str = "", status: str = "active") -> None:
        now = self._now()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO subscriptions (user_id, stripe_customer_id, stripe_subscription_id, tier, status, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        stripe_customer_id = EXCLUDED.stripe_customer_id,
                        stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                        tier = EXCLUDED.tier,
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, stripe_customer_id, stripe_sub_id, tier, status, now),
                )
                cur.execute(
                    "UPDATE users SET subscription_tier = %s WHERE user_id = %s",
                    (tier, user_id),
                )
            conn.commit()

    def has_consent(self, user_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM user_consent WHERE user_id = %s", (user_id,))
                return cur.fetchone() is not None

    def record_consent(self, user_id: str, privacy_version: str = "1.0") -> None:
        now = self._now()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_consent (user_id, consented_at, privacy_version)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id, now, privacy_version),
                )
            conn.commit()

    def record_feedback(self, user_id: str, rating: int, correlation_id: str = "") -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO reply_feedback (user_id, correlation_id, rating) VALUES (%s, %s, %s)",
                    (user_id, correlation_id, rating),
                )
            conn.commit()

    def get_language(self, user_id: str) -> str:
        data = self.get_personal_data(user_id)
        return data.get("preferred_language", "en")

    def set_language(self, user_id: str, lang: str) -> None:
        self.set_personal_field(user_id, "preferred_language", lang)

    # Override SQLite-specific methods with PostgreSQL implementations
    def purge_expired(self) -> None:
        now = self._now()
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT user_id FROM users WHERE expires_at <= %s", (now,))
                expired = cur.fetchall()
                for row in expired:
                    self.clear_user(row["user_id"], conn=conn)
            conn.commit()

    def is_expired(self, user_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT expires_at FROM users WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
        if not row:
            return False
        return row[0] <= self._now()

    def touch_user(self, user_id: str) -> None:
        self.purge_expired()
        self._ensure_user(user_id)

    def _ensure_user(self, user_id: str) -> None:
        now = self._now()
        expires = self._expires_at()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (user_id, created_at, expires_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET expires_at = EXCLUDED.expires_at
                    """,
                    (user_id, now, expires),
                )
            conn.commit()

    def set_personal_field(self, user_id: str, field_name: str, value: str) -> None:
        if not value.strip():
            return
        self.touch_user(user_id)
        now = self._now()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO personal_data (user_id, field_name, field_value, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, field_name) DO UPDATE SET
                        field_value = EXCLUDED.field_value,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, field_name, value.strip(), now),
                )
            conn.commit()

    def get_personal_data(self, user_id: str) -> dict[str, str]:
        self.purge_expired()
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT field_name, field_value FROM personal_data WHERE user_id = %s",
                    (user_id,),
                )
                rows = cur.fetchall()
        return {row["field_name"]: row["field_value"] for row in rows}

    def get_case_state(self, user_id: str) -> dict:
        self.purge_expired()
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM case_state WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
        if not row:
            return {
                "country": "",
                "visa_type": "",
                "process_name": "",
                "documents_provided": [],
                "missing_documents": [],
                "next_steps": [],
            }
        return {
            "country": row["country"] or "",
            "visa_type": row["visa_type"] or "",
            "process_name": row["process_name"] or "",
            "documents_provided": json.loads(row["documents_provided"] or "[]"),
            "missing_documents": json.loads(row["missing_documents"] or "[]"),
            "next_steps": json.loads(row["next_steps"] or "[]"),
        }

    def update_case_state(self, user_id: str, **fields: str | list[str]) -> None:
        self.touch_user(user_id)
        current = self.get_case_state(user_id)
        for key, value in fields.items():
            if value is None:
                continue
            if key in ("documents_provided", "missing_documents", "next_steps"):
                current[key] = value if isinstance(value, list) else current.get(key, [])
            else:
                current[key] = str(value) if value else current.get(key, "")
        now = self._now()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO case_state (
                        user_id, country, visa_type, process_name,
                        documents_provided, missing_documents, next_steps, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        country = EXCLUDED.country,
                        visa_type = EXCLUDED.visa_type,
                        process_name = EXCLUDED.process_name,
                        documents_provided = EXCLUDED.documents_provided,
                        missing_documents = EXCLUDED.missing_documents,
                        next_steps = EXCLUDED.next_steps,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        user_id,
                        current.get("country", ""),
                        current.get("visa_type", ""),
                        current.get("process_name", ""),
                        json.dumps(current.get("documents_provided", [])),
                        json.dumps(current.get("missing_documents", [])),
                        json.dumps(current.get("next_steps", [])),
                        now,
                    ),
                )
            conn.commit()

    def add_uploaded_file(self, user_id: str, filename: str, file_path: str, media_type: str = "") -> None:
        self.touch_user(user_id)
        now = self._now()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO uploaded_files (user_id, filename, file_path, media_type, uploaded_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, filename, file_path, media_type, now),
                )
            conn.commit()

    def get_uploaded_files(self, user_id: str) -> list[dict[str, str]]:
        self.purge_expired()
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT filename, file_path, media_type, uploaded_at::text FROM uploaded_files WHERE user_id = %s ORDER BY uploaded_at",
                    (user_id,),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def clear_user(self, user_id: str, conn=None) -> None:
        def _clear(c) -> None:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT file_path FROM uploaded_files WHERE user_id = %s", (user_id,))
                files = cur.fetchall()
                cur.execute("DELETE FROM personal_data WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM case_state WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM uploaded_files WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM user_consent WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            for row in files:
                try:
                    Path(row["file_path"]).unlink(missing_ok=True)
                except OSError:
                    pass
            upload_dir = UPLOADS_DIR / _safe_id(user_id)
            if upload_dir.exists():
                for p in upload_dir.iterdir():
                    try:
                        p.unlink(missing_ok=True)
                    except OSError:
                        pass

        if conn:
            _clear(conn)
        else:
            with self._connect() as c:
                _clear(c)
                c.commit()

    def retention_notice(self) -> str:
        return (
            f"I will save your data securely for {self._retention_hours} hours so I can help you fill in forms. "
            f"After {self._retention_hours} hours, all data and files are automatically deleted."
        )

    # Reuse parsing logic from parent via same method bodies
    extract_fields_from_message = UserDataStore.extract_fields_from_message
    infer_case_updates = UserDataStore.infer_case_updates
    format_context_for_llm = UserDataStore.format_context_for_llm
