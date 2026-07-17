"""SQLite-backed session store + feedback storage."""

from __future__ import annotations
import sqlite3
import json
import time
import os
from datetime import datetime
from app.config import get_settings

settings = get_settings()


class Database:
    """SQLite database for sessions, messages, and feedback."""
    
    _conn: sqlite3.Connection | None = None

    @classmethod
    def get(cls) -> sqlite3.Connection:
        if cls._conn is None:
            db_dir = os.path.dirname(settings.sqlite_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            cls._conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
            cls._conn.row_factory = sqlite3.Row
            cls._conn.execute("PRAGMA journal_mode=WAL")
            cls._conn.execute("PRAGMA foreign_keys=ON")
            cls._init_tables(cls._conn)
        return cls._conn

    @staticmethod
    def _init_tables(conn: sqlite3.Connection):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                summary TEXT DEFAULT '',
                sentiment_trend TEXT DEFAULT '[]',
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                ended_at TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT DEFAULT '',
                confidence REAL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                rating TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
        """)
        conn.commit()

    @classmethod
    def close(cls):
        if cls._conn:
            cls._conn.close()
            cls._conn = None


# ── Session operations ──

def create_session(session_id: str, user_id: str) -> None:
    db = Database.get()
    db.execute(
        "INSERT OR IGNORE INTO sessions (id, user_id, created_at) VALUES (?, ?, ?)",
        (session_id, user_id, datetime.utcnow().isoformat())
    )
    db.commit()


def session_exists(session_id: str) -> bool:
    db = Database.get()
    row = db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row is not None


def add_message_db(session_id: str, role: str, content: str, intent: str = "", confidence: float = 0) -> int:
    db = Database.get()
    cur = db.execute(
        "INSERT INTO messages (session_id, role, content, intent, confidence, created_at) VALUES (?,?,?,?,?,?)",
        (session_id, role, content, intent, confidence, datetime.utcnow().isoformat())
    )
    db.commit()
    return cur.lastrowid


def get_messages(session_id: str, limit: int = 20) -> list[dict]:
    db = Database.get()
    rows = db.execute(
        "SELECT role, content, intent, confidence FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit)
    ).fetchall()
    return [{"role": r["role"], "content": r["content"], "intent": r["intent"], "confidence": r["confidence"]} for r in reversed(rows)]


def update_session_summary(session_id: str, summary: str) -> None:
    db = Database.get()
    db.execute("UPDATE sessions SET summary = ? WHERE id = ?", (summary, session_id))
    db.commit()


def get_session_summary(session_id: str) -> str:
    db = Database.get()
    row = db.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row["summary"] if row else ""


def update_session_trend(session_id: str, trend: list) -> None:
    db = Database.get()
    db.execute("UPDATE sessions SET sentiment_trend = ? WHERE id = ?", (json.dumps(trend), session_id))
    db.commit()


def get_session_trend(session_id: str) -> list:
    db = Database.get()
    row = db.execute("SELECT sentiment_trend FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return json.loads(row["sentiment_trend"]) if row else []


def close_session(session_id: str) -> None:
    db = Database.get()
    db.execute("UPDATE sessions SET status = 'closed', ended_at = ? WHERE id = ?",
               (datetime.utcnow().isoformat(), session_id))
    db.commit()


# ── Feedback ──

def save_feedback(session_id: str, message_index: int, rating: str) -> None:
    db = Database.get()
    db.execute(
        "INSERT INTO feedback (session_id, message_index, rating, created_at) VALUES (?,?,?,?)",
        (session_id, message_index, rating, datetime.utcnow().isoformat())
    )
    db.commit()


def get_feedback_stats() -> dict:
    db = Database.get()
    total = db.execute("SELECT COUNT(*) as c FROM feedback").fetchone()["c"]
    good = db.execute("SELECT COUNT(*) as c FROM feedback WHERE rating = 'up'").fetchone()["c"]
    return {"total": total, "up": good, "down": total - good}
