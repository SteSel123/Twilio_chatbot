"""Conversation analytics, response times, and FAQ tracking."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from config import BASE_DIR

ANALYTICS_DB = BASE_DIR / ".user_data" / "analytics.db"


def _connect() -> sqlite3.Connection:
    ANALYTICS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ANALYTICS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                intent TEXT DEFAULT '',
                response_ms REAL DEFAULT 0,
                message_preview TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_messages_tenant_ts ON messages(tenant_id, ts);
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                interest TEXT DEFAULT '',
                budget TEXT DEFAULT '',
                urgency TEXT DEFAULT '',
                score INTEGER DEFAULT 0,
                labels TEXT DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_leads_tenant_ts ON leads(tenant_id, ts);
            CREATE TABLE IF NOT EXISTS tenant_usage (
                tenant_id TEXT NOT NULL,
                month_key TEXT NOT NULL,
                conversation_count INTEGER DEFAULT 0,
                PRIMARY KEY (tenant_id, month_key)
            );
            """
        )


def record_message(
    tenant_id: str,
    user_id: str,
    direction: str,
    *,
    intent: str = "",
    response_ms: float = 0,
    message_preview: str = "",
) -> None:
    _init_db()
    preview = message_preview[:200]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO messages (ts, tenant_id, user_id, direction, intent, response_ms, message_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (time.time(), tenant_id, user_id, direction, intent, response_ms, preview),
        )
        if direction == "inbound":
            month_key = time.strftime("%Y-%m")
            conn.execute(
                """
                INSERT INTO tenant_usage (tenant_id, month_key, conversation_count)
                VALUES (?, ?, 1)
                ON CONFLICT(tenant_id, month_key) DO UPDATE SET
                    conversation_count = conversation_count + 1
                """,
                (tenant_id, month_key),
            )


def record_lead(
    tenant_id: str,
    user_id: str,
    *,
    interest: str = "",
    budget: str = "",
    urgency: str = "",
    score: int = 0,
    labels: list[str] | None = None,
) -> None:
    _init_db()
    import json

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO leads (ts, tenant_id, user_id, interest, budget, urgency, score, labels)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                tenant_id,
                user_id,
                interest,
                budget,
                urgency,
                score,
                json.dumps(labels or []),
            ),
        )


def get_monthly_conversations(tenant_id: str) -> int:
    _init_db()
    month_key = time.strftime("%Y-%m")
    with _connect() as conn:
        row = conn.execute(
            "SELECT conversation_count FROM tenant_usage WHERE tenant_id = ? AND month_key = ?",
            (tenant_id, month_key),
        ).fetchone()
    return int(row["conversation_count"]) if row else 0


def get_dashboard_stats(tenant_id: str, days: int = 30) -> dict:
    _init_db()
    since = time.time() - days * 86400
    with _connect() as conn:
        inbound = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE tenant_id = ? AND direction = 'inbound' AND ts >= ?",
            (tenant_id, since),
        ).fetchone()["c"]
        outbound = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE tenant_id = ? AND direction = 'outbound' AND ts >= ?",
            (tenant_id, since),
        ).fetchone()["c"]
        avg_ms = conn.execute(
            """
            SELECT AVG(response_ms) AS avg_ms FROM messages
            WHERE tenant_id = ? AND direction = 'outbound' AND response_ms > 0 AND ts >= ?
            """,
            (tenant_id, since),
        ).fetchone()["avg_ms"]
        top_intents = conn.execute(
            """
            SELECT intent, COUNT(*) AS c FROM messages
            WHERE tenant_id = ? AND direction = 'inbound' AND intent != '' AND ts >= ?
            GROUP BY intent ORDER BY c DESC LIMIT 8
            """,
            (tenant_id, since),
        ).fetchall()
        top_questions = conn.execute(
            """
            SELECT message_preview, COUNT(*) AS c FROM messages
            WHERE tenant_id = ? AND direction = 'inbound' AND message_preview != '' AND ts >= ?
            GROUP BY message_preview ORDER BY c DESC LIMIT 10
            """,
            (tenant_id, since),
        ).fetchall()
        leads = conn.execute(
            """
            SELECT COUNT(*) AS c, AVG(score) AS avg_score FROM leads
            WHERE tenant_id = ? AND ts >= ?
            """,
            (tenant_id, since),
        ).fetchone()
        hot_leads = conn.execute(
            """
            SELECT user_id, interest, budget, urgency, score, labels, ts FROM leads
            WHERE tenant_id = ? AND ts >= ? ORDER BY score DESC LIMIT 20
            """,
            (tenant_id, since),
        ).fetchall()

    return {
        "period_days": days,
        "inbound_messages": inbound,
        "outbound_messages": outbound,
        "avg_response_ms": round(float(avg_ms or 0), 1),
        "avg_response_sec": round(float(avg_ms or 0) / 1000, 2),
        "monthly_conversations": get_monthly_conversations(tenant_id),
        "top_intents": [{"intent": r["intent"], "count": r["c"]} for r in top_intents],
        "top_questions": [{"question": r["message_preview"], "count": r["c"]} for r in top_questions],
        "leads_count": leads["c"] if leads else 0,
        "leads_avg_score": round(float(leads["avg_score"] or 0), 1) if leads else 0,
        "hot_leads": [
            {
                "user_id": r["user_id"],
                "interest": r["interest"],
                "budget": r["budget"],
                "urgency": r["urgency"],
                "score": r["score"],
                "labels": r["labels"],
            }
            for r in hot_leads
        ],
    }
