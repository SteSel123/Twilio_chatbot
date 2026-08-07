"""Local SQL storage for user personal data and case state (12-hour retention)."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import DATA_DIR, DATA_RETENTION_HOURS, DB_PATH, DEFAULT_TENANT_ID, UPLOADS_DIR
from patterns import SERVICE_TYPE_PATTERN, TOPIC_PATTERN

FORM_FIELDS = (
    "full_name", "date_of_birth", "nationality", "passport_number",
    "passport_issue_date", "passport_expiry_date", "current_address",
    "destination_address", "email", "phone", "employer", "employment_type",
    "salary", "purpose_of_stay", "duration_of_stay",
)

PERSONAL_FIELD_ALIASES = {
    "full_name": ("full name", "name", "passport name"),
    "date_of_birth": ("date of birth", "dob", "birth date", "born"),
    "nationality": ("nationality", "citizen of", "citizenship"),
    "passport_number": ("passport number", "passport no", "passport #"),
    "passport_issue_date": ("passport issue", "issued on", "issue date"),
    "passport_expiry_date": ("passport expiry", "expires on", "expiry date", "expiration"),
    "current_address": ("current address", "home address", "address in"),
    "destination_address": ("address in destination", "address in spain", "address in germany"),
    "email": ("email", "e-mail"),
    "phone": ("phone", "mobile", "telephone"),
    "employer": ("employer", "company", "employed by"),
    "employment_type": ("contract type", "employment type", "job type"),
    "salary": ("salary", "income", "monthly pay"),
    "purpose_of_stay": ("purpose of stay", "reason for stay", "moving for"),
    "duration_of_stay": ("duration of stay", "how long", "stay duration"),
    "employment_status": ("employment status", "employed", "self-employed", "student"),
}

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s\-()]{7,}\d)")
KEY_VALUE_PATTERN = re.compile(r"^([a-zA-Z\s_]+)\s*[:=]\s*(.+)$", re.M)


def _storage_key(user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    return f"{tenant_id}::{user_id}"


class UserDataStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS personal_data (
                    user_id TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    field_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
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
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS uploaded_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    media_type TEXT DEFAULT '',
                    uploaded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_consent (
                    user_id TEXT PRIMARY KEY,
                    consented_at TEXT NOT NULL,
                    privacy_version TEXT DEFAULT '1.0'
                );
                CREATE TABLE IF NOT EXISTS reply_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    correlation_id TEXT,
                    rating INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id TEXT PRIMARY KEY,
                    stripe_customer_id TEXT,
                    stripe_subscription_id TEXT,
                    tier TEXT DEFAULT 'free',
                    status TEXT DEFAULT 'inactive',
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _expires_at(self) -> datetime:
        return self._now() + timedelta(hours=DATA_RETENTION_HOURS)

    def _ensure_user(self, user_id: str) -> None:
        now = self._now().isoformat()
        expires = self._expires_at().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, created_at, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET expires_at = excluded.expires_at
                """,
                (user_id, now, expires),
            )

    def purge_expired(self) -> None:
        now = self._now().isoformat()
        with self._connect() as conn:
            expired = conn.execute(
                "SELECT user_id FROM users WHERE expires_at <= ?", (now,)
            ).fetchall()
            for row in expired:
                self.clear_user(row["user_id"], conn=conn)
            conn.commit()

    def is_expired(self, user_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT expires_at FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return False
        return row["expires_at"] <= self._now().isoformat()

    def touch_user(self, user_id: str) -> None:
        self.purge_expired()
        self._ensure_user(user_id)

    def set_personal_field(self, user_id: str, field_name: str, value: str) -> None:
        if not value.strip():
            return
        self.touch_user(user_id)
        now = self._now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO personal_data (user_id, field_name, field_value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, field_name) DO UPDATE SET
                    field_value = excluded.field_value,
                    updated_at = excluded.updated_at
                """,
                (user_id, field_name, value.strip(), now),
            )

    def get_personal_data(self, user_id: str) -> dict[str, str]:
        self.purge_expired()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT field_name, field_value FROM personal_data WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {row["field_name"]: row["field_value"] for row in rows}

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
        now = self._now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO case_state (
                    user_id, country, visa_type, process_name,
                    documents_provided, missing_documents, next_steps, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    country = excluded.country,
                    visa_type = excluded.visa_type,
                    process_name = excluded.process_name,
                    documents_provided = excluded.documents_provided,
                    missing_documents = excluded.missing_documents,
                    next_steps = excluded.next_steps,
                    updated_at = excluded.updated_at
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

    def get_case_state(self, user_id: str) -> dict:
        self.purge_expired()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM case_state WHERE user_id = ?", (user_id,)
            ).fetchone()
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

    def add_uploaded_file(
        self, user_id: str, filename: str, file_path: str, media_type: str = ""
    ) -> None:
        self.touch_user(user_id)
        now = self._now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO uploaded_files (user_id, filename, file_path, media_type, uploaded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, filename, file_path, media_type, now),
            )

    def get_uploaded_files(self, user_id: str) -> list[dict[str, str]]:
        self.purge_expired()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT filename, file_path, media_type, uploaded_at FROM uploaded_files WHERE user_id = ? ORDER BY uploaded_at",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def extract_fields_from_message(self, user_id: str, message: str) -> list[str]:
        """Parse obvious personal details from free-text user messages."""
        updated: list[str] = []
        lower = message.lower()

        email = EMAIL_PATTERN.search(message)
        if email:
            self.set_personal_field(user_id, "email", email.group(0))
            updated.append("email")

        phone = PHONE_PATTERN.search(message)
        if phone and "whatsapp" not in lower:
            self.set_personal_field(user_id, "phone", phone.group(0).strip())
            updated.append("phone")

        for match in KEY_VALUE_PATTERN.finditer(message):
            raw_key = match.group(1).strip().lower()
            value = match.group(2).strip()
            for field, aliases in PERSONAL_FIELD_ALIASES.items():
                if raw_key in aliases or raw_key.replace("_", " ") in aliases:
                    self.set_personal_field(user_id, field, value)
                    updated.append(field)
                    break

        for field, aliases in PERSONAL_FIELD_ALIASES.items():
            for alias in aliases:
                pattern = rf"{re.escape(alias)}\s*(?:is|:)\s*(.+?)(?:\.|$|\n)"
                m = re.search(pattern, lower, re.I)
                if m:
                    self.set_personal_field(user_id, field, m.group(1).strip())
                    if field not in updated:
                        updated.append(field)

        return updated

    def infer_case_updates(self, user_id: str, message: str) -> None:
        """Update customer context from message keywords (generic SMB)."""
        state = self.get_case_state(user_id)
        topic = TOPIC_PATTERN.search(message)
        if topic:
            state["country"] = topic.group(0).title()

        service = SERVICE_TYPE_PATTERN.search(message)
        if service:
            state["process_name"] = service.group(0)

        service_match = re.search(
            r"\b(booking|appointment|order|quote|support|delivery|takeaway|consultation|"
            r"membership|subscription|repair|installation)\b",
            message,
            re.I,
        )
        if service_match:
            state["visa_type"] = service_match.group(0)

        item_keywords = (
            "receipt", "invoice", "photo", "document", "id", "proof", "reference",
            "confirmation", "menu", "catalogue", "spec sheet",
        )
        lower = message.lower()
        for item in item_keywords:
            if item in lower and any(w in lower for w in ("attached", "sent", "uploaded", "here is", "i have", "photo of")):
                if item not in state["documents_provided"]:
                    state["documents_provided"].append(item)

        self.update_case_state(user_id, **state)

    def clear_user(self, user_id: str, conn: sqlite3.Connection | None = None) -> None:
        def _clear(c: sqlite3.Connection) -> None:
            c.execute("DELETE FROM personal_data WHERE user_id = ?", (user_id,))
            c.execute("DELETE FROM case_state WHERE user_id = ?", (user_id,))
            c.execute("DELETE FROM user_consent WHERE user_id = ?", (user_id,))
            files = c.execute(
                "SELECT file_path FROM uploaded_files WHERE user_id = ?", (user_id,)
            ).fetchall()
            c.execute("DELETE FROM uploaded_files WHERE user_id = ?", (user_id,))
            c.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
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
                try:
                    upload_dir.rmdir()
                except OSError:
                    pass

        if conn:
            _clear(conn)
        else:
            with self._connect() as c:
                _clear(c)

    def format_context_for_llm(self, user_id: str) -> str:
        personal = self.get_personal_data(user_id)
        case = self.get_case_state(user_id)
        files = self.get_uploaded_files(user_id)

        parts: list[str] = []
        if case.get("country") or case.get("visa_type") or case.get("process_name"):
            parts.append("## Customer context")
            if case.get("country"):
                parts.append(f"- Topic / request: {case['country']}")
            if case.get("visa_type"):
                parts.append(f"- Service type: {case['visa_type']}")
            if case.get("process_name"):
                parts.append(f"- Detail: {case['process_name']}")
            if case.get("documents_provided"):
                parts.append(f"- Items provided: {', '.join(case['documents_provided'])}")
            if case.get("missing_documents"):
                parts.append(f"- Items still needed: {', '.join(case['missing_documents'])}")
            if case.get("next_steps"):
                parts.append(f"- Next steps: {'; '.join(case['next_steps'])}")

        if personal:
            parts.append("\n## Stored personal data (12-hour retention)")
            for key, value in personal.items():
                parts.append(f"- {key.replace('_', ' ').title()}: {value}")

        if files:
            parts.append("\n## Uploaded files on disk")
            for f in files:
                parts.append(f"- {f['filename']} ({f['media_type']}) saved at {f['uploaded_at']}")

        missing_fields = [f for f in FORM_FIELDS if f not in personal]
        if missing_fields:
            parts.append("\n## Time estimate hint")
            mins = min(2 + len(missing_fields), 20)
            parts.append(
                f"- About {mins} minutes remain if filling a form "
                f"({len(missing_fields)} personal fields still needed)."
            )

        if not parts:
            return ""
        return "\n".join(parts)

    def retention_notice(self) -> str:
        return (
            f"I will save your data securely for {DATA_RETENTION_HOURS} hours so I can help you fill in forms. "
            f"After {DATA_RETENTION_HOURS} hours, all data and files are automatically deleted."
        )

    def has_consent(self, user_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM user_consent WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row is not None

    def record_consent(self, user_id: str, privacy_version: str = "1.0") -> None:
        now = self._now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_consent (user_id, consented_at, privacy_version)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, now, privacy_version),
            )

    def record_feedback(self, user_id: str, rating: int, correlation_id: str = "") -> None:
        now = self._now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reply_feedback (user_id, correlation_id, rating, created_at) VALUES (?, ?, ?, ?)",
                (user_id, correlation_id, rating, now),
            )

    def get_subscription_tier(self, user_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT tier FROM subscriptions WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row["tier"] if row else "free"

    def set_subscription(
        self, user_id: str, tier: str, stripe_customer_id: str = "", stripe_sub_id: str = "", status: str = "active"
    ) -> None:
        now = self._now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO subscriptions (user_id, stripe_customer_id, stripe_subscription_id, tier, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    stripe_customer_id = excluded.stripe_customer_id,
                    stripe_subscription_id = excluded.stripe_subscription_id,
                    tier = excluded.tier,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (user_id, stripe_customer_id, stripe_sub_id, tier, status, now),
            )

    def get_language(self, user_id: str) -> str:
        return self.get_personal_data(user_id).get("preferred_language", "en")

    def set_language(self, user_id: str, lang: str) -> None:
        self.set_personal_field(user_id, "preferred_language", lang)


def _safe_id(user_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
