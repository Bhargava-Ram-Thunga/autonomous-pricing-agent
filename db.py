"""SQLite persistence layer — undo store + key-value memory.
Used as fallback when POSTGRES_URI is not configured.
All operations are thread-safe and silent-fail.
"""
import sqlite3
import json
import os
import threading
from pathlib import Path

_DB_PATH = Path(os.environ.get("SQLITE_PATH", "data/agent.db"))
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS kv_store (
                service TEXT NOT NULL,
                key     TEXT NOT NULL,
                value   TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (service, key)
            );
            CREATE TABLE IF NOT EXISTS undo_store (
                trip_id    TEXT PRIMARY KEY,
                action     TEXT,
                prev_state TEXT,
                service_number TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        _conn.commit()
    return _conn


# ── KV STORE (remember / recall) ─────────────────────────────────────────────

def kv_set(service: str, key: str, value) -> None:
    try:
        with _lock:
            _get_conn().execute(
                """INSERT INTO kv_store (service, key, value, updated_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(service, key) DO UPDATE
                   SET value=excluded.value, updated_at=excluded.updated_at""",
                (service, key, json.dumps(value))
            )
            _get_conn().commit()
    except Exception:
        pass


def kv_get(service: str, key: str):
    try:
        with _lock:
            row = _get_conn().execute(
                "SELECT value FROM kv_store WHERE service=? AND key=?",
                (service, key)
            ).fetchone()
        return json.loads(row["value"]) if row else None
    except Exception:
        return None


def kv_del(service: str, key: str) -> None:
    try:
        with _lock:
            _get_conn().execute(
                "DELETE FROM kv_store WHERE service=? AND key=?",
                (service, key)
            )
            _get_conn().commit()
    except Exception:
        pass


# ── UNDO STORE ────────────────────────────────────────────────────────────────

def undo_save(trip_id: str, action: str, prev_state: dict, service_number: str = "") -> None:
    try:
        with _lock:
            _get_conn().execute(
                """INSERT INTO undo_store (trip_id, action, prev_state, service_number, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(trip_id) DO UPDATE
                   SET action=excluded.action, prev_state=excluded.prev_state,
                       service_number=excluded.service_number, updated_at=excluded.updated_at""",
                (str(trip_id), action, json.dumps(prev_state), service_number)
            )
            _get_conn().commit()
    except Exception:
        pass


def undo_get(trip_id: str) -> dict | None:
    try:
        with _lock:
            row = _get_conn().execute(
                "SELECT action, prev_state, service_number FROM undo_store WHERE trip_id=?",
                (str(trip_id),)
            ).fetchone()
        if not row:
            return None
        return {
            "action": row["action"],
            "prev_state": json.loads(row["prev_state"]) if row["prev_state"] else {},
            "service_number": row["service_number"],
        }
    except Exception:
        return None


def undo_delete(trip_id: str) -> None:
    try:
        with _lock:
            _get_conn().execute(
                "DELETE FROM undo_store WHERE trip_id=?",
                (str(trip_id),)
            )
            _get_conn().commit()
    except Exception:
        pass


def undo_load_all() -> dict:
    """Load entire undo store into memory dict on startup."""
    try:
        with _lock:
            rows = _get_conn().execute(
                "SELECT trip_id, action, prev_state, service_number FROM undo_store"
            ).fetchall()
        return {
            r["trip_id"]: {
                "action": r["action"],
                "prev_state": json.loads(r["prev_state"]) if r["prev_state"] else {},
                "service_number": r["service_number"],
            }
            for r in rows
        }
    except Exception:
        return {}
