"""Persistent state store — Postgres ai schema.

NEW TABLES (readable, with column comments):
  service_memory    — ops team notes per service (remember/recall)
  booking_snapshots — periodic seat booking counts per service
  fare_action_log   — every fare/classification change by the agent
  undo_log          — last reversible action per trip (survives restart)
  surge_log         — every AI surge event with before/after fares
  autoloop_runs     — history of every autoloop execution

LEGACY TABLES (kept for backward compatibility):
  agent_kv, bookings_history, outcomes, undo_store
"""
import os
import json
from typing import Any
from psycopg import Connection
from psycopg.rows import dict_row

_conn: Connection | None = None


def is_available() -> bool:
    return bool(os.environ.get("POSTGRES_URI", "").strip())


def _get_conn() -> Connection:
    global _conn
    if _conn is not None and not _conn.closed:
        return _conn
    uri = os.environ.get("POSTGRES_URI", "")
    if not uri:
        raise RuntimeError("POSTGRES_URI not set")
    _conn = Connection.connect(uri, autocommit=True, prepare_threshold=0, row_factory=dict_row)
    with _conn.cursor() as cur:
        # Legacy tables — kept as-is
        cur.execute("CREATE SCHEMA IF NOT EXISTS ai")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.agent_kv (
            service TEXT NOT NULL, key TEXT NOT NULL, value JSONB,
            updated_at TIMESTAMP DEFAULT NOW(), PRIMARY KEY (service, key)
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.outcomes (
            id SERIAL PRIMARY KEY, service TEXT NOT NULL, tool TEXT NOT NULL,
            args JSONB, booked_before INT, booked_after INT,
            classification_before TEXT, classification_after TEXT,
            window_min INT, score REAL, ts TIMESTAMP DEFAULT NOW()
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.bookings_history (
            service TEXT NOT NULL, ts TIMESTAMP DEFAULT NOW(),
            booked INT, classification TEXT
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bookings_svc_ts ON ai.bookings_history(service, ts)")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.undo_store (
            trip_id TEXT PRIMARY KEY, action TEXT, prev_state JSONB,
            service_number TEXT, updated_at TIMESTAMP DEFAULT NOW()
        )""")

        # New readable tables
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.service_memory (
            service_number TEXT NOT NULL, note_key TEXT NOT NULL,
            note_value JSONB, created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (service_number, note_key)
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.booking_snapshots (
            id SERIAL PRIMARY KEY, service_number TEXT NOT NULL,
            snapshot_at TIMESTAMP DEFAULT NOW(), seats_booked INTEGER,
            total_seats INTEGER DEFAULT 45, classification TEXT
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_booking_snapshots_svc ON ai.booking_snapshots(service_number, snapshot_at)")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.fare_action_log (
            id SERIAL PRIMARY KEY, service_number TEXT NOT NULL,
            trip_id TEXT, action_type TEXT NOT NULL, action_args JSONB,
            seats_booked_before INTEGER, seats_booked_after INTEGER,
            class_before TEXT, class_after TEXT,
            outcome_score REAL, check_after_minutes INTEGER DEFAULT 30,
            triggered_by TEXT DEFAULT 'autoloop',
            actioned_at TIMESTAMP DEFAULT NOW()
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fare_action_log_svc ON ai.fare_action_log(service_number, actioned_at)")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.undo_log (
            trip_id TEXT PRIMARY KEY, service_number TEXT,
            action_type TEXT, previous_state JSONB,
            recorded_at TIMESTAMP DEFAULT NOW()
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.surge_log (
            id SERIAL PRIMARY KEY, trip_id TEXT NOT NULL,
            service_number TEXT NOT NULL, trigger_reason TEXT,
            multiplier REAL, fare_min_before INTEGER, fare_max_before INTEGER,
            fare_min_after INTEGER, fare_max_after INTEGER,
            seats_left INTEGER, velocity_per_hr REAL, hours_to_depart REAL,
            surged_at TIMESTAMP DEFAULT NOW()
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_surge_log_svc ON ai.surge_log(service_number, surged_at)")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.autoloop_runs (
            id SERIAL PRIMARY KEY, run_at TIMESTAMP DEFAULT NOW(),
            journey_date DATE, route TEXT,
            services_checked INTEGER DEFAULT 0, services_changed INTEGER DEFAULT 0,
            services_skipped INTEGER DEFAULT 0, services_errored INTEGER DEFAULT 0,
            total_seats_booked INTEGER DEFAULT 0, total_seats INTEGER DEFAULT 0,
            fill_pct REAL, duration_seconds REAL, notes TEXT
        )""")
        # User-route assignments — each Slack user can have their own route
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.user_routes (
            slack_user_id TEXT PRIMARY KEY,
            display_name  TEXT,
            source        TEXT NOT NULL,
            destination   TEXT NOT NULL,
            assigned_at   TIMESTAMP DEFAULT NOW(),
            assigned_by   TEXT DEFAULT 'admin'
        )""")
        # Pricing learning — action → outcome feedback loop
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai.pricing_learning (
            id                    SERIAL PRIMARY KEY,
            service_number        TEXT NOT NULL,
            trip_id               TEXT,
            action_type           TEXT NOT NULL,
            classification        TEXT,
            model_classification  TEXT,
            manual_classification TEXT,
            fare_delta_pct        INTEGER DEFAULT 0,
            seats_booked_before   INTEGER DEFAULT 0,
            seats_booked_after    INTEGER,
            booking_delta         INTEGER,
            hours_to_depart       REAL,
            day_of_week           INTEGER,
            score                 REAL,
            outcome               TEXT,
            triggered_by          TEXT DEFAULT 'autoloop',
            actioned_at           TIMESTAMP DEFAULT NOW(),
            evaluated_at          TIMESTAMP
        )""")
        # Add columns if table already exists (migration)
        for col, defn in [
            ("model_classification",  "TEXT"),
            ("manual_classification", "TEXT"),
            ("triggered_by",          "TEXT DEFAULT 'autoloop'"),
        ]:
            try:
                cur.execute(f"ALTER TABLE ai.pricing_learning ADD COLUMN IF NOT EXISTS {col} {defn}")
            except Exception:
                pass
        cur.execute("CREATE INDEX IF NOT EXISTS idx_learning_svc ON ai.pricing_learning(service_number, actioned_at)")
    return _conn


# ── PRICING LEARNING ──────────────────────────────────────────────────────────

def learn_record_action(service_number: str, trip_id: str, action_type: str,
                        classification: str = "",
                        model_classification: str = "",
                        manual_classification: str = "",
                        fare_delta_pct: int = 0,
                        seats_booked_before: int = 0, hours_to_depart: float = 72.0,
                        day_of_week: int = 0,
                        triggered_by: str = "autoloop") -> int | None:
    """Record a pricing action. Returns row id for later evaluation.
    model_classification  = what the matrix/AI recommended
    manual_classification = what a human operator set (if overriding)
    triggered_by          = 'autoloop' | 'ai_agent' | 'manual' | 'slack'
    """
    if not is_available():
        return None
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            INSERT INTO ai.pricing_learning
              (service_number, trip_id, action_type, classification,
               model_classification, manual_classification, fare_delta_pct,
               seats_booked_before, hours_to_depart, day_of_week, triggered_by, actioned_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            RETURNING id
            """, (service_number, str(trip_id), action_type, classification,
                  model_classification, manual_classification,
                  fare_delta_pct, seats_booked_before, hours_to_depart, day_of_week, triggered_by))
            row = cur.fetchone()
            return row["id"] if row else None
    except Exception as e:
        print(f"[learn] record_action error: {e}")
        return None


def learn_evaluate(record_id: int, seats_booked_after: int):
    """Evaluate outcome of a recorded action. Score: +1 good, -1 bad, 0 neutral."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("SELECT seats_booked_before, action_type FROM ai.pricing_learning WHERE id=%s",
                        (record_id,))
            row = cur.fetchone()
            if not row:
                return
            before = row["seats_booked_before"]
            delta  = seats_booked_after - before
            # Score: bookings increased after action = good (+1), decreased = bad (-1)
            if delta > 0:
                score, outcome = 1.0, "positive"
            elif delta < -1:
                score, outcome = -1.0, "negative"
            else:
                score, outcome = 0.0, "neutral"
            cur.execute("""
            UPDATE ai.pricing_learning
            SET seats_booked_after=%s, booking_delta=%s, score=%s, outcome=%s, evaluated_at=NOW()
            WHERE id=%s
            """, (seats_booked_after, delta, score, outcome, record_id))
    except Exception as e:
        print(f"[learn] evaluate error: {e}")


def learn_get_insight(service_number: str, action_type: str = "",
                      day_of_week: int = -1, limit: int = 20) -> dict:
    """Return learning insights for a service.
    Returns avg score, best/worst actions, recommendation.
    """
    if not is_available():
        return {}
    try:
        with _get_conn().cursor() as cur:
            conditions = ["service_number=%s", "evaluated_at IS NOT NULL"]
            params = [service_number]
            if action_type:
                conditions.append("action_type=%s")
                params.append(action_type)
            if day_of_week >= 0:
                conditions.append("day_of_week=%s")
                params.append(day_of_week)
            where = " AND ".join(conditions)
            cur.execute(f"""
            SELECT action_type, classification, fare_delta_pct,
                   AVG(score) as avg_score, COUNT(*) as count,
                   SUM(CASE WHEN outcome='positive' THEN 1 ELSE 0 END) as positives,
                   SUM(CASE WHEN outcome='negative' THEN 1 ELSE 0 END) as negatives
            FROM ai.pricing_learning
            WHERE {where}
            GROUP BY action_type, classification, fare_delta_pct
            ORDER BY avg_score DESC
            LIMIT %s
            """, params + [limit])
            rows = cur.fetchall()
            if not rows:
                return {"insight": "no data yet", "records": 0}
            best  = max(rows, key=lambda r: r["avg_score"])
            worst = min(rows, key=lambda r: r["avg_score"])
            total = sum(r["count"] for r in rows)
            return {
                "service": service_number,
                "total_evaluated": total,
                "best_action": {
                    "type": best["action_type"],
                    "classification": best["classification"],
                    "avg_score": round(float(best["avg_score"]),2),
                    "count": best["count"],
                },
                "worst_action": {
                    "type": worst["action_type"],
                    "classification": worst["classification"],
                    "avg_score": round(float(worst["avg_score"]),2),
                    "count": worst["count"],
                },
                "rows": [dict(r) for r in rows],
            }
    except Exception as e:
        print(f"[learn] get_insight error: {e}")
        return {}


def learn_should_avoid(service_number: str, action_type: str,
                       classification: str, day_of_week: int = -1) -> bool:
    """Return True if this action historically led to negative outcomes on this service."""
    if not is_available():
        return False
    try:
        with _get_conn().cursor() as cur:
            params = [service_number, action_type, classification]
            day_filter = ""
            if day_of_week >= 0:
                day_filter = "AND day_of_week=%s"
                params.append(day_of_week)
            cur.execute(f"""
            SELECT AVG(score) as avg_score, COUNT(*) as cnt
            FROM ai.pricing_learning
            WHERE service_number=%s AND action_type=%s AND classification=%s
              AND evaluated_at IS NOT NULL {day_filter}
            """, params)
            row = cur.fetchone()
            if row and row["cnt"] >= 3:  # need at least 3 data points
                return float(row["avg_score"]) < -0.3  # consistently negative
    except Exception:
        pass
    return False


# ── USER ROUTE MANAGEMENT ─────────────────────────────────────────────────────

def user_route_set(slack_user_id: str, source: str, destination: str,
                   display_name: str = "", assigned_by: str = "admin"):
    """Assign a route to a Slack user. Upserts on conflict."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            INSERT INTO ai.user_routes (slack_user_id, display_name, source, destination, assigned_at, assigned_by)
            VALUES (%s, %s, %s, %s, NOW(), %s)
            ON CONFLICT (slack_user_id) DO UPDATE
            SET source=EXCLUDED.source, destination=EXCLUDED.destination,
                display_name=EXCLUDED.display_name,
                assigned_at=NOW(), assigned_by=EXCLUDED.assigned_by
            """, (slack_user_id, display_name or slack_user_id, source.upper(), destination.upper(), assigned_by))
    except Exception as e:
        print(f"[state_store] user_route_set error: {e}")


def user_route_get(slack_user_id: str) -> tuple[str, str] | None:
    """Return (source, destination) for user, or None if not assigned."""
    if not is_available():
        return None
    try:
        with _get_conn().cursor() as cur:
            cur.execute(
                "SELECT source, destination FROM ai.user_routes WHERE slack_user_id=%s",
                (slack_user_id,)
            )
            row = cur.fetchone()
            if row:
                return row["source"], row["destination"]
    except Exception as e:
        print(f"[state_store] user_route_get error: {e}")
    return None


def user_route_delete(slack_user_id: str):
    """Remove route assignment — user falls back to global default."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("DELETE FROM ai.user_routes WHERE slack_user_id=%s", (slack_user_id,))
    except Exception as e:
        print(f"[state_store] user_route_delete error: {e}")


def user_route_list() -> list[dict]:
    """Return all user-route assignments."""
    if not is_available():
        return []
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            SELECT slack_user_id, display_name, source, destination,
                   assigned_at, assigned_by
            FROM ai.user_routes ORDER BY assigned_at DESC
            """)
            return cur.fetchall()
    except Exception as e:
        print(f"[state_store] user_route_list error: {e}")
        return []


# ── UNDO LOG (new) ────────────────────────────────────────────────────────────

def undo_save(trip_id: str, action: str, prev_state: dict, service_number: str = ""):
    """Save last reversible action per trip to undo_log (and legacy undo_store)."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            # New table
            cur.execute("""
            INSERT INTO ai.undo_log (trip_id, service_number, action_type, previous_state, recorded_at)
            VALUES (%s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (trip_id) DO UPDATE
            SET service_number=EXCLUDED.service_number, action_type=EXCLUDED.action_type,
                previous_state=EXCLUDED.previous_state, recorded_at=NOW()
            """, (str(trip_id), service_number, action, json.dumps(prev_state)))
            # Legacy table
            cur.execute("""
            INSERT INTO ai.undo_store (trip_id, action, prev_state, service_number, updated_at)
            VALUES (%s, %s, %s::jsonb, %s, NOW())
            ON CONFLICT (trip_id) DO UPDATE
            SET action=EXCLUDED.action, prev_state=EXCLUDED.prev_state,
                service_number=EXCLUDED.service_number, updated_at=NOW()
            """, (str(trip_id), action, json.dumps(prev_state), service_number))
    except Exception:
        pass


def undo_get(trip_id: str) -> dict | None:
    if not is_available():
        return None
    try:
        with _get_conn().cursor() as cur:
            cur.execute(
                "SELECT action_type, previous_state, service_number FROM ai.undo_log WHERE trip_id=%s",
                (str(trip_id),)
            )
            r = cur.fetchone()
            if not r:
                return None
            return {
                "action": r["action_type"],
                "prev_state": r["previous_state"] or {},
                "service_number": r["service_number"],
            }
    except Exception:
        return None


def undo_delete(trip_id: str):
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("DELETE FROM ai.undo_log WHERE trip_id=%s", (str(trip_id),))
            cur.execute("DELETE FROM ai.undo_store WHERE trip_id=%s", (str(trip_id),))
    except Exception:
        pass


def undo_load_all() -> dict:
    """Load entire undo store into memory on startup."""
    if not is_available():
        return {}
    try:
        with _get_conn().cursor() as cur:
            cur.execute("SELECT trip_id, action_type, previous_state, service_number FROM ai.undo_log")
            rows = cur.fetchall()
        return {
            r["trip_id"]: {
                "action": r["action_type"],
                "prev_state": r["previous_state"] or {},
                "service_number": r["service_number"],
            }
            for r in rows
        }
    except Exception:
        return {}


# ── SERVICE MEMORY — remember/recall (new) ────────────────────────────────────

def kv_set(service: str, key: str, value: Any):
    """Store a note for a service (ops team remember command)."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            # New table
            cur.execute("""
            INSERT INTO ai.service_memory (service_number, note_key, note_value, created_at, updated_at)
            VALUES (%s, %s, %s::jsonb, NOW(), NOW())
            ON CONFLICT (service_number, note_key) DO UPDATE
            SET note_value=EXCLUDED.note_value, updated_at=NOW()
            """, (service, key, json.dumps(value)))
            # Legacy table
            cur.execute("""
            INSERT INTO ai.agent_kv (service, key, value, updated_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (service, key) DO UPDATE
            SET value=EXCLUDED.value, updated_at=NOW()
            """, (service, key, json.dumps(value)))
    except Exception:
        pass


def kv_get(service: str, key: str) -> Any:
    """Recall a note for a service."""
    if not is_available():
        return None
    try:
        with _get_conn().cursor() as cur:
            cur.execute(
                "SELECT note_value FROM ai.service_memory WHERE service_number=%s AND note_key=%s",
                (service, key)
            )
            r = cur.fetchone()
            return r["note_value"] if r else None
    except Exception:
        return None


def kv_del(service: str, key: str):
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("DELETE FROM ai.service_memory WHERE service_number=%s AND note_key=%s", (service, key))
            cur.execute("DELETE FROM ai.agent_kv WHERE service=%s AND key=%s", (service, key))
    except Exception:
        pass


# ── BOOKING SNAPSHOTS (new) ───────────────────────────────────────────────────

def record_booking(service: str, booked: int, classification: str | None,
                   total_seats: int = 45):
    """Record a booking count snapshot."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            # New table
            cur.execute("""
            INSERT INTO ai.booking_snapshots (service_number, seats_booked, total_seats, classification)
            VALUES (%s, %s, %s, %s)
            """, (service, booked, total_seats, classification))
            # Legacy table
            cur.execute("""
            INSERT INTO ai.bookings_history (service, booked, classification)
            VALUES (%s, %s, %s)
            """, (service, booked, classification))
    except Exception:
        pass


def recent_bookings(service: str, since_min: int = 60) -> list[dict]:
    if not is_available():
        return []
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            SELECT seats_booked AS booked, classification, snapshot_at AS ts
            FROM ai.booking_snapshots
            WHERE service_number=%s AND snapshot_at >= NOW() - (%s || ' minutes')::interval
            ORDER BY snapshot_at ASC
            """, (service, str(since_min)))
            return cur.fetchall()
    except Exception:
        return []


# ── FARE ACTION LOG (new) ─────────────────────────────────────────────────────

def record_fare_action(service_number: str, trip_id: str, action_type: str,
                       action_args: dict, seats_booked_before: int,
                       class_before: str, triggered_by: str = "autoloop"):
    """Log a fare or classification change."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            INSERT INTO ai.fare_action_log
                (service_number, trip_id, action_type, action_args,
                 seats_booked_before, class_before, triggered_by, actioned_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, NOW())
            """, (service_number, str(trip_id), action_type,
                  json.dumps(action_args), seats_booked_before,
                  class_before, triggered_by))
    except Exception:
        pass


def record_outcome(service: str, tool: str, args: dict,
                   booked_before: int, classification_before: str | None,
                   booked_after: int = None, classification_after: str = None,
                   window_min: int = 30, score: float = None):
    """Legacy outcome recording — still writes to ai.outcomes."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            INSERT INTO ai.outcomes (service, tool, args, booked_before, booked_after,
                                      classification_before, classification_after,
                                      window_min, score)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
            """, (service, tool, json.dumps(args), booked_before, booked_after,
                  classification_before, classification_after, window_min, score))
    except Exception:
        pass


def evaluate_pending_outcomes(window_min: int = 30):
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            SELECT id, service, booked_before, ts FROM ai.outcomes
            WHERE booked_after IS NULL
              AND ts <= NOW() - (%s || ' minutes')::interval
            """, (str(window_min),))
            pending = cur.fetchall()
            for row in pending:
                cur.execute("""
                SELECT booked, classification FROM ai.bookings_history
                WHERE service=%s ORDER BY ts DESC LIMIT 1
                """, (row["service"],))
                latest = cur.fetchone()
                if not latest:
                    continue
                delta = (latest["booked"] or 0) - (row["booked_before"] or 0)
                score = delta / max(window_min / 60, 0.5)
                cur.execute("""
                UPDATE ai.outcomes SET booked_after=%s, classification_after=%s, score=%s
                WHERE id=%s
                """, (latest["booked"], latest["classification"], score, row["id"]))
    except Exception:
        pass


def recent_outcomes(service: str | None = None, limit: int = 20) -> list[dict]:
    if not is_available():
        return []
    try:
        with _get_conn().cursor() as cur:
            if service:
                cur.execute("""
                SELECT * FROM ai.outcomes WHERE service=%s ORDER BY ts DESC LIMIT %s
                """, (service, limit))
            else:
                cur.execute("SELECT * FROM ai.outcomes ORDER BY ts DESC LIMIT %s", (limit,))
            return cur.fetchall()
    except Exception:
        return []


# ── SURGE LOG (new) ───────────────────────────────────────────────────────────

def record_surge(trip_id: str, service_number: str, trigger_reason: str,
                 multiplier: float, fare_min_before: int, fare_max_before: int,
                 fare_min_after: int, fare_max_after: int,
                 seats_left: int, velocity_per_hr: float, hours_to_depart: float):
    """Log an AI surge event."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            INSERT INTO ai.surge_log
                (trip_id, service_number, trigger_reason, multiplier,
                 fare_min_before, fare_max_before, fare_min_after, fare_max_after,
                 seats_left, velocity_per_hr, hours_to_depart)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (str(trip_id), service_number, trigger_reason, multiplier,
                  fare_min_before, fare_max_before, fare_min_after, fare_max_after,
                  seats_left, velocity_per_hr, hours_to_depart))
    except Exception:
        pass


# ── AUTOLOOP RUNS (new) ───────────────────────────────────────────────────────

def record_autoloop_run(journey_date, route: str, services_checked: int,
                        services_changed: int, services_skipped: int,
                        services_errored: int, total_seats_booked: int,
                        total_seats: int, fill_pct: float,
                        duration_seconds: float, notes: str = ""):
    """Log one autoloop execution."""
    if not is_available():
        return
    try:
        with _get_conn().cursor() as cur:
            cur.execute("""
            INSERT INTO ai.autoloop_runs
                (journey_date, route, services_checked, services_changed,
                 services_skipped, services_errored, total_seats_booked,
                 total_seats, fill_pct, duration_seconds, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (journey_date, route, services_checked, services_changed,
                  services_skipped, services_errored, total_seats_booked,
                  total_seats, fill_pct, duration_seconds, notes))
    except Exception:
        pass
