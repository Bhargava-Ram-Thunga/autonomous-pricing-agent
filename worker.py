"""Booking history & velocity tracking — shared across agent, autoloop, slack.
No Playwright. All portal actions go through api_client.py.
"""
import time as _t
import threading

# In-memory booking history: {service_number: [(ts, booked), ...]}
_HISTORY: dict[str, list[tuple[float, int]]] = {}
_lock = threading.Lock()

_bootstrapped = False
_MIN_RECORD_INTERVAL = 60  # skip duplicate entries within 60s


def _bootstrap_from_db():
    global _bootstrapped
    with _lock:
        if _bootstrapped:
            return
        # Set flag only after successful load (or confirmed unavailable)
        try:
            from state_store import _get_conn, is_available
            if not is_available():
                _bootstrapped = True
                return
            with _get_conn().cursor() as cur:
                cur.execute("SET search_path TO ai, public")
                cur.execute("""
                SELECT service, booked, EXTRACT(EPOCH FROM ts) AS ts_epoch
                FROM ai.bookings_history
                WHERE ts >= NOW() - INTERVAL '24 hours'
                ORDER BY ts ASC
                """)
                for r in cur.fetchall():
                    _HISTORY.setdefault(r["service"], []).append(
                        (float(r["ts_epoch"]), r["booked"]))
            print(f"[worker] bootstrapped history for {len(_HISTORY)} services")
        except Exception as e:
            print(f"[worker] bootstrap skipped ({e}) — history starts fresh")
        finally:
            _bootstrapped = True


def record_bookings(svcs: list[dict]):
    """Record current booking counts for all services. Deduplicates within 60s."""
    _bootstrap_from_db()
    now = _t.time()
    with _lock:
        for s in svcs:
            sn = s.get("service_number")
            if not sn:
                continue
            h = _HISTORY.setdefault(sn, [])
            # Skip if last entry was within MIN_RECORD_INTERVAL seconds (dedup)
            if h and (now - h[-1][0]) < _MIN_RECORD_INTERVAL:
                continue
            h.append((now, int(s.get("booked") or 0)))
            # Trim entries older than 24h
            cutoff = now - 86400
            _HISTORY[sn] = [(t, b) for t, b in h if t >= cutoff]
    # Persist to Postgres
    try:
        from state_store import record_booking
        for s in svcs:
            sn = s.get("service_number")
            if sn:
                record_booking(sn, int(s.get("booked") or 0), s.get("classification"))
    except Exception:
        pass


def booking_velocity(service_number: str, window_min: int = 60) -> dict:
    """Return {booked_now, booked_then, delta, window_min, per_hour}."""
    _bootstrap_from_db()
    h = _HISTORY.get(service_number, [])
    if not h:
        return {"error": f"no history for {service_number}"}
    now_ts, now_b = h[-1]
    cutoff = now_ts - window_min * 60
    # Find entry with timestamp closest to cutoff from BELOW (last entry before window start)
    # This gives accurate delta over the full window, not just since first-after-cutoff
    prior_b = h[0][1]  # default: oldest available entry
    for ts, b in h:
        if ts <= cutoff:
            prior_b = b   # keep updating — want the latest entry at/before cutoff
        else:
            break
    delta = now_b - prior_b
    per_hour = (delta * 60 / window_min) if window_min else 0
    return {"booked_now": now_b, "booked_then": prior_b, "delta": delta,
            "window_min": window_min, "per_hour": round(per_hour, 1)}
