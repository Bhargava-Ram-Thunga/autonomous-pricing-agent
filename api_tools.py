"""LangChain Tools — direct HTTP via api_client.py (no Playwright, no browser).
Same tool names/signatures as tools.py so agent.py and autoloop.py need no changes.
"""
import json
from datetime import datetime
from pathlib import Path
from langchain_core.tools import tool
from api_client import get_client
import route_config as _rc
from pricing_rules import (
    can_reprice, mark_repriced, cooldown_remaining,
    needs_reclassification, clamp_fare, FARE_FLOOR, FARE_CEILING,
)

CHANGES_LOG = Path("changes.jsonl")
WRITE_TOOLS = {"set_pricing_model", "bulk_adjust", "static_fare",
               "global_fare_adjustment", "global_pricing_model"}

def _delta_str(a):
    try:
        d = int(float(a.get("delta", 0)))
        return ("increased" if d > 0 else "decreased"), abs(d)
    except (TypeError, ValueError):
        return "adjusted", 0

_ACTION_LABELS = {
    "set_pricing_model":      lambda a: f"Set pricing -> model={a.get('model','')}, class={a.get('classification','')}",
    "bulk_adjust":            lambda a: f"Fare {_delta_str(a)[0]} by Rs.{_delta_str(a)[1]} on all seats",
    "static_fare":            lambda a: f"Fixed fares -> seats {a.get('seats', [])} set to Rs.{a.get('fare', '')}",
    "global_fare_adjustment": lambda a: f"Global fare {_delta_str(a)[0]} Rs.{_delta_str(a)[1]} on {a.get('services', 'all services')}",
    "global_pricing_model":   lambda a: f"Global pricing -> {a.get('classification', '')} set on {a.get('services', 'all services')}",
}


def _route():
    return _rc.get_route()


def _record_for_undo(trip_id: int, action: str, prev_state: dict, service_number: str = ""):
    """Persist pre-change state so slack_listener undo handler can reverse it."""
    try:
        import slack_listener as _sl
        with _sl._last_action_lock:
            _sl._last_action[str(trip_id)] = {
                "action": action,
                "prev_state": prev_state,
                "service_number": service_number,
            }
    except Exception:
        pass
    # Also persist to Postgres so undo survives restart
    try:
        from state_store import undo_save
        undo_save(str(trip_id), action, prev_state, service_number)
    except Exception:
        pass


def _audit(tool_name: str, args: dict, result: str):
    if tool_name not in WRITE_TOOLS:
        return
    ts = datetime.now().isoformat(timespec="seconds")
    rec = {"ts": ts, "tool": tool_name, "args": args, "result": result}
    with CHANGES_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    label = _ACTION_LABELS.get(tool_name, lambda a: tool_name)(args)
    print(f"[action] {datetime.now().strftime('%H:%M:%S')} | {label}")
    try:
        from state_store import record_outcome
        record_outcome("", tool_name, args, 0, None)
    except Exception:
        pass


# ── READ TOOLS ──────────────────────────────────────────────────────────────

@tool
def search_services(source: str = "", destination: str = "", journey_date: str = "") -> str:
    """Search trips by source/destination on a date — reads from Postgres.
    journey_date format YYYY-MM-DD. Defaults: configured route, today."""
    from datetime import datetime as _dt, date as _d
    from api_client import _station_id
    dsrc, ddst = _route()
    src = source or dsrc
    dst = destination or ddst
    jd = _d.today()
    if journey_date:
        try:
            jd = _dt.strptime(journey_date, "%Y-%m-%d").date()
        except Exception:
            pass
    try:
        from postgres_reader import get_trips
        src_id = _station_id(src)
        dst_id = _station_id(dst)
        trips = get_trips(src_id, dst_id, jd)
        # Store in api_client — including last_journey_date for list_services
        c = get_client()
        c._last_source       = src
        c._last_dest         = dst
        c._last_journey_date = jd  # remembered so list_services uses correct date
        c._trips = [{
            "id": t["trip_id"], "serviceNumber": t["service_number"],
            "fareClassification": t["classification"], "pricingModel": t["pricing_model"],
            "active": t["active"], "ticketsBooked": t["booked"],
            "totalSeats": t["total_seats"], "journeyDate": str(t["journey_date"]),
            "departureTime": t["first_boarding"].isoformat() if t.get("first_boarding") else "",
        } for t in trips]
        print(f"[pg] found {len(trips)} trips on {jd} (Postgres)")
        return f"found {len(trips)} trips"
    except Exception as e:
        # Fallback to API
        print(f"[pg] search_services fallback to API: {e}")
        c = get_client()
        return c.search_services(src, dst, journey_date=jd)


@tool
def list_services() -> str:
    """JSON list of services from last search — reads from Postgres."""
    try:
        from postgres_reader import get_trips
        from api_client import _station_id, get_client as _gc
        from datetime import date as _d
        c = _gc()
        src = c._last_source
        dst = c._last_dest
        src_id = _station_id(src)
        dst_id = _station_id(dst)
        # Use journey_date from last search_services call — not today
        jd_ls = getattr(c, "_last_journey_date", None) or _d.today()
        trips = get_trips(src_id, dst_id, jd_ls)
        svcs = []
        for t in trips:
            dep = t.get("first_boarding")
            last_bp = t.get("last_boarding")
            import re as _re
            svc_m = _re.search(r"(\d{4}(?:-\d+)?(?:\s*OPT)?)\s*$", t.get("service_number",""), _re.I)
            short = svc_m.group(1).strip() if svc_m else t.get("service_number","").split("-")[-1]
            svcs.append({
                "svc": short,
                "id": t["trip_id"],
                "bkd": t["booked"] or 0,
                "seats": t["total_seats"] or 45,
                "cls": t["classification"] or "",
                "dep": dep.strftime("%H:%M") if dep else "",
                "lbp": last_bp.strftime("%H:%M") if last_bp else "",
            })
        try:
            from worker import record_bookings
            record_bookings(svcs)
        except Exception:
            pass
        return json.dumps(svcs)
    except Exception as e:
        print(f"[pg] list_services fallback to API: {e}")
        c = get_client()
        svcs_raw = c.list_services()
        try:
            from worker import record_bookings
            record_bookings(svcs_raw)
        except Exception:
            pass
        import re as _re2
        svcs = []
        for t in svcs_raw:
            svc_m = _re2.search(r"(\d{4}(?:-\d+)?(?:\s*OPT)?)\s*$", t.get("service_number",""), _re2.I)
            short2 = svc_m.group(1).strip() if svc_m else t.get("service_number","").split("-")[-1]
            svcs.append({
                "svc": short2,
                "id": t.get("trip_id") or t.get("id"),
                "bkd": t.get("booked") or t.get("ticketsBooked") or 0,
                "seats": t.get("total_seats") or t.get("totalSeats") or 45,
                "cls": t.get("classification") or t.get("fareClassification") or "",
                "dep": (t.get("departure_time") or t.get("departureTime") or "")[:5],
                "lbp": (t.get("last_boarding") or "")[:5],
            })
        return json.dumps(svcs)


@tool
def get_default_route() -> str:
    """Return current default route."""
    src, dst = _route()
    return f"{src} → {dst}"


@tool
def set_default_route(source: str, destination: str) -> str:
    """Change the live default route (persists across restarts)."""
    return _rc.set_route(source, destination)


@tool
def read_seat_fares(trip_id: str) -> str:
    """Return JSON map of {seat_number: fare} for a trip ID — reads from Postgres."""
    try:
        from postgres_reader import get_trip_seats
        seats = get_trip_seats(int(trip_id))
        result = {}
        for s in seats:
            name = str(s.get("seat_name") or s.get("seat_number") or s["id"])
            result[name] = float(s.get("total_fare") or 0)
        return json.dumps(result)
    except Exception as e:
        print(f"[pg] read_seat_fares fallback: {e}")
        c = get_client()
        return json.dumps(c.read_seat_fares(int(trip_id)))


@tool
def get_seat_layout(trip_id: str) -> str:
    """Return seat layout for a trip — reads from Postgres.
    Each entry: {id, name, type, category, fare, occupied, x, y, is_dummy, has_static_fare}.
    category = 'window' | 'non_window' | 'last_row'.
    Use 'id' field (integer) when calling static_fare — NOT 'name'.
    Summary line prepended: e.g. '45 seats: 10 window, 30 non_window, 5 last_row'"""
    try:
        from postgres_reader import get_trip_seats
        from collections import Counter
        tid = int(trip_id)
        rows = get_trip_seats(tid)
        if not rows:
            return f"no seat data for trip {tid}"
        # Determine categories (same logic as api_client.py)
        non_dummy = [r for r in rows if not r.get("is_dummy")]
        all_x = [r.get("x", 0) for r in non_dummy]
        max_x = max(all_x) if all_x else 0
        is_sleeper = any("sleeper" in str(r.get("seat_type","")).lower() for r in non_dummy)
        from collections import Counter as _C
        if not is_sleeper:
            main = [r for r in non_dummy if r.get("x",0) != max_x]
            y_counts = _C(r.get("y",0) for r in main)
            regular_ys = sorted(y for y,cnt in y_counts.items() if cnt > 1)
            window_ys = {regular_ys[0], regular_ys[-1]} if len(regular_ys) >= 2 else set()
        layout = []
        for r in rows:
            sx, sy = r.get("x",0), r.get("y",0)
            st = str(r.get("seat_type","")).lower()
            is_d = bool(r.get("is_dummy"))
            if is_sleeper:
                if sx == max_x: cat = "last_row"
                elif "shared" in st: cat = "non_window"
                elif "sleeper" in st: cat = "window"
                else: cat = "non_window"
            else:
                if sx == max_x: cat = "last_row"
                elif sy in window_ys: cat = "window"
                else: cat = "non_window"
            layout.append({
                "id": r["id"],
                "name": str(r.get("seat_name") or r.get("seat_number") or r["id"]),
                "type": r.get("seat_type",""),
                "category": cat,
                "fare": float(r.get("total_fare") or 0),
                "occupied": not bool(r.get("available", True)),
                "blocked": False,
                "has_static_fare": bool(r.get("has_static_fare")),
                "is_dummy": is_d,
                "x": sx, "y": sy,
            })
        cats = Counter(s["category"] for s in layout)
        summary = f"{len(layout)} seats: {cats.get('window',0)} window, {cats.get('non_window',0)} non_window, {cats.get('last_row',0)} last_row"
        return summary + "\n" + json.dumps(layout)
    except Exception as e:
        print(f"[pg] get_seat_layout fallback: {e}")
        c = get_client()
        tid = int(trip_id)
        layout = c.get_seat_layout(tid)
        if not layout:
            return f"no seat data for trip {tid}"
        from collections import Counter
        cats = Counter(s["category"] for s in layout)
        summary = f"{len(layout)} seats: {cats.get('window',0)} window, {cats.get('non_window',0)} non_window, {cats.get('last_row',0)} last_row"
        return summary + "\n" + json.dumps(layout)


@tool
def get_trip_fares(trip_id: str) -> str:
    """Return fare adjustment info for a trip."""
    c = get_client()
    data = c.get_trip_fares(int(trip_id))
    return json.dumps(data)


@tool
def get_fare_history(trip_id: str) -> str:
    """Return fare change history for a trip — reads from Postgres."""
    try:
        from postgres_reader import get_fare_history as _pg_fare_hist
        data = _pg_fare_hist(int(trip_id))
        return json.dumps(data, default=str)
    except Exception as e:
        print(f"[pg] get_fare_history fallback: {e}")
        c = get_client()
        return json.dumps(c.get_fare_history(int(trip_id)), default=str)


@tool
def get_booking_velocity(service_number: str, window_min: int = 60) -> str:
    """Return booking rate for service over last window_min minutes.
    Returns JSON {booked_now, booked_then, delta, per_hour}."""
    try:
        from worker import booking_velocity
        return json.dumps(booking_velocity(service_number, int(window_min)))
    except Exception:
        return json.dumps({"error": "velocity data unavailable"})


@tool
def get_recent_outcomes(service_number: str = "", limit: int = 10) -> str:
    """Return recent past pricing actions and their booking-delta outcome scores."""
    from state_store import recent_outcomes, evaluate_pending_outcomes
    try:
        evaluate_pending_outcomes(window_min=30)
    except Exception:
        pass
    rows = recent_outcomes(service_number or None, limit)
    for r in rows:
        if r.get("ts"):
            r["ts"] = r["ts"].isoformat(timespec="seconds")
    return json.dumps(rows, default=str)


@tool
def remember(service_number: str, key: str, value: str) -> str:
    """Persist a note/decision/observation for a service."""
    from state_store import kv_set
    kv_set(service_number, key, value)
    return f"saved {service_number}.{key}={value}"


@tool
def recall(service_number: str, key: str) -> str:
    """Retrieve a previously saved note for a service."""
    from state_store import kv_get
    v = kv_get(service_number, key)
    return json.dumps(v)


@tool
def query_database(sql: str) -> str:
    """Run a read-only SQL query against the PricingCo staging Postgres database.
    Use for any data question not covered by other tools.
    Tables available (public schema):
      Trips - trip_id, serviceNumber, journeyDate, fareClassification, pricingModel, totalOccupency, totalRevenue, asp
      TripSeats - tripId, seatId, fare, available, hasStaticFare
      TripSeatFareHistory - tripId, seatId, fare, createdAt, pricingModel
      TripClassificationHistory - tripId, fareClassification, pricingModel, createdAt
      TripBoardingPoints - tripId, boardingPointId, scheduledTime, prime
      BoardingPoints - id, name, stationId, landmark
      Stations - id, name, shortName
      Services - id, serviceNumber, name, sourceId, destinationId
      Passengers - id, name, mobile (masked)
      Seats - id, name, positionX, positionY, seatType
      TripDiscounts, TripFareHistory, CompetitorSeatPricing
      ai.pricing_learning - service_number, classification, model_classification, score, outcome, actioned_at
      ai.autoloop_runs - journey_date, route, services_changed, fill_pct, run_at
      ai.surge_log - service_number, multiplier, velocity_per_hr, surged_at
    Only SELECT queries allowed. Use LIMIT to avoid large results."""
    try:
        from state_store import _get_conn
        conn = _get_conn()
        # Safety: only allow SELECT
        clean = sql.strip().upper()
        if not clean.startswith("SELECT") and not clean.startswith("WITH"):
            return "ERROR: Only SELECT queries allowed"
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchmany(100)  # max 100 rows
            if not rows:
                return "No results found"
            return json.dumps(rows, default=str)
    except Exception as e:
        return f"Query error: {e}"


@tool
def call_mcp_tool(tool_name: str, arguments: str = "{}") -> str:
    """Call any tool on the PricingCo MCP server (dashboard.example-portal.com/api/mcp).
    Available tools:
      pricing_dashboard_service  — future occupancy % per service per date (ClickHouse)
      pricing_alerts             — open pricing alerts from ClickHouse
      pricing_dashboard_filters  — list valid routes for pricing_dashboard_service
      pricing_set_classification — set fareClassification + model on a trip
      pricing_fare_adjustment    — apply % fare adjustment to a trip
      pricing_set_static_fare    — lock exact fare on specific seats
      pricing_reset_static_fare  — clear all static fares from a trip
      pricing_agent_rules        — matrix lookup: classification for seats/day/hours
    arguments: JSON string of tool input e.g. '{"src":"BANGALORE","dst":"TIRUPATI","from":"2026-06-10","to":"2026-06-20"}'
    """
    import os, requests, json as _json
    dashboard_url = os.environ.get("SALES_DASHBOARD_URL", "https://dashboard.example-portal.com").rstrip("/")
    mcp_key = os.environ.get("SALES_DASHBOARD_MCP_KEY", "")
    try:
        args = _json.loads(arguments) if isinstance(arguments, str) else arguments
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
            "id": 1,
        }
        resp = requests.post(
            f"{dashboard_url}/api/mcp",
            json=payload,
            headers={
                "x-api-key": mcp_key,
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if not resp.ok:
            return f"MCP error: HTTP {resp.status_code} — {resp.text[:200]}"
        data = resp.json()
        result = data.get("result", {})
        content = result.get("content", [])
        if content:
            return content[0].get("text", _json.dumps(result))
        return _json.dumps(result, default=str)
    except Exception as e:
        return f"call_mcp_tool error: {e}"


@tool
def get_pricing_alerts() -> str:
    """Fetch open pricing alerts from the PricingCo sales dashboard.
    Returns alerts flagged by the system: low occupancy vs target,
    fare above market, demand spikes, anomalies across upcoming services.
    Use this at the start of each pricing run to check for urgent issues."""
    import os, requests
    dashboard_url = os.environ.get("SALES_DASHBOARD_URL", "https://dashboard.example-portal.com").rstrip("/")
    mcp_key = os.environ.get("SALES_DASHBOARD_MCP_KEY", "")
    try:
        headers = {"x-internal-key": mcp_key} if mcp_key else {}
        resp = requests.get(f"{dashboard_url}/api/pricing-alerts", headers=headers, timeout=10)
        if not resp.ok:
            return f"pricing_alerts unavailable: HTTP {resp.status_code}"
        return json.dumps(resp.json(), default=str)
    except Exception as e:
        return f"pricing_alerts error: {e}"


@tool
def get_revenue_metrics(trip_id: str) -> str:
    """Return Revenue, ASP, unsold ASP, EPK for a trip — reads from Postgres."""
    try:
        from postgres_reader import get_revenue_metrics as _pg_rev
        from api_client import get_route_distance_km, get_client as _gc
        c = _gc()
        km = get_route_distance_km(c._last_source, c._last_dest)
        return json.dumps(_pg_rev(int(trip_id), route_km=km), default=str)
    except Exception as e:
        print(f"[pg] get_revenue_metrics fallback: {e}")
        c = get_client()
        return json.dumps(c.get_revenue_metrics(int(trip_id)), default=str)


@tool
def get_last_boarding_time(trip_id: str) -> str:
    """Return last boarding point name and time (IST) for a trip — reads from Postgres."""
    try:
        from postgres_reader import get_boarding_points as _pg_bp
        points = _pg_bp(int(trip_id))
        if not points:
            return f"no boarding points for trip {trip_id}"
        last = points[-1]
        raw_t = last.get("scheduled_time") or last.get("current_time")
        ist_str = ""
        if raw_t:
            from datetime import timezone, timedelta
            ist = timezone(timedelta(hours=5, minutes=30))
            if hasattr(raw_t, 'astimezone'):
                ist_str = raw_t.astimezone(ist).strftime("%I:%M %p")
            else:
                ist_str = str(raw_t)
        return json.dumps({
            "name": last.get("name",""),
            "station": last.get("station",""),
            "time_ist": ist_str,
            "raw": raw_t.isoformat() if hasattr(raw_t,'isoformat') else str(raw_t),
        }, default=str)
    except Exception as e:
        print(f"[pg] get_last_boarding_time fallback: {e}")
        c = get_client()
        result = c.get_last_boarding_time(int(trip_id))
        if not result:
            return f"no boarding points found for trip {trip_id}"
        return json.dumps(result)


@tool
def get_boarding_points(trip_id: str) -> str:
    """Return all boarding points with times (IST) for a trip, ordered by time — reads from Postgres."""
    try:
        from postgres_reader import get_boarding_points as _pg_bp
        from datetime import timezone, timedelta
        _IST = timezone(timedelta(hours=5, minutes=30))
        points = _pg_bp(int(trip_id))
        if not points:
            return f"no boarding points for trip {trip_id}"
        result = []
        for p in points:
            raw_t = p.get("scheduled_time") or p.get("current_time")
            ist_str = ""
            if raw_t:
                try:
                    ist_str = raw_t.astimezone(_IST).strftime("%I:%M %p")
                except Exception:
                    ist_str = str(raw_t)
            result.append({
                "name":    p.get("name",""),
                "station": p.get("station",""),
                "time":    ist_str,
                "prime":   bool(p.get("prime", False)),
            })
        return json.dumps(result, default=str)
    except Exception as e:
        print(f"[pg] get_boarding_points fallback: {e}")
        c = get_client()
        points = c.get_boarding_points(int(trip_id))
        if not points:
            return f"no boarding points for trip {trip_id}"
        return json.dumps(points, default=str)


# ── WRITE TOOLS ─────────────────────────────────────────────────────────────

@tool
def set_pricing_model(trip_id: str, model: str = "", classification: str = "",
                      current_classification: str = "") -> str:
    """Set Pricing Model and/or Fare Classification on a trip.
    classification: super low / low / medium / high / super high / ultra high / festive
    model: automation v1 / automation v2 / automation v3 / automation v4 / model v1 / model v2 / sciative
    current_classification: pass current value to enable idempotency check (skip if already correct)."""
    tid = int(trip_id)

    # Idempotency: skip if already at target classification
    if classification and current_classification:
        if not needs_reclassification(current_classification, classification):
            return f"skip: trip {tid} already at {current_classification} — no change needed"

    # Cooldown: skip if repriced too recently
    if not can_reprice(tid):
        remaining = cooldown_remaining(tid)
        return f"skip: trip {tid} in cooldown — {remaining//60}m {remaining%60}s remaining"

    c = get_client()
    # Capture prev state before writing (for undo)
    try:
        trips = c.list_services()
        curr_trip = next((t for t in trips if t.get("trip_id") == tid), None)
        prev_model = curr_trip.get("model", "") if curr_trip else ""
        prev_cls   = curr_trip.get("classification", current_classification) if curr_trip else current_classification
        svc_num    = curr_trip.get("service_number", str(tid)) if curr_trip else str(tid)
    except Exception:
        prev_model, prev_cls, svc_num = "", current_classification, str(tid)
    _record_for_undo(tid, "set_pricing_model",
                     {"model": prev_model, "classification": prev_cls}, svc_num)

    r = c.set_pricing_model(tid, model=model, classification=classification)
    mark_repriced(tid)
    label = f"{current_classification} -> {classification}" if current_classification else classification
    _audit("set_pricing_model", {"trip_id": tid, "model": model, "classification": label}, r)

    # Record for learning — track who decided + what matrix would have said
    try:
        from state_store import learn_record_action
        from pricing_rules import matrix_result
        from postgres_reader import get_trips
        from api_client import _station_id
        from datetime import date as _d
        import threading

        # triggered_by: autoloop thread = autoloop, else slack/human
        _tname = threading.current_thread().name
        _by = "autoloop" if "autoloop" in _tname.lower() else "manual"

        # Get matrix recommendation for this trip (what AI/rules would say)
        _matrix_cls = ""
        try:
            _trip_row = get_trips(_station_id(c._last_source), _station_id(c._last_dest), _d.today())
            _tr = next((t for t in _trip_row if t.get("trip_id") == tid), None)
            if _tr:
                from autoloop import _parse_dep_dt
                from datetime import datetime as _dtnow
                _dep = _parse_dep_dt(str(_tr.get("first_boarding") or ""))
                _hrs = (_dep - _dtnow.now()).total_seconds()/3600 if _dep else 72.0
                _dow = _d.today().weekday()
                import re as _re_m
                _svc_m = _re_m.search(r"\d{4}", svc_num)
                _hhmm = int(_svc_m.group()) if _svc_m else 9999
                if _dow == 5 and _hhmm <= 700: _dow = 4
                _mc, _ = matrix_result(int(_tr.get("booked") or 0), _dow, _hrs)
                _matrix_cls = _mc or "static"
        except Exception:
            _matrix_cls = classification  # unknown → use applied

        # manual_classification = non-empty only when human overrides
        _manual = classification if _by == "manual" else ""
        # is_override = human set different from what matrix recommends
        _is_override = _by == "manual" and _matrix_cls and _matrix_cls != classification.lower()

        learn_record_action(
            svc_num, str(tid), "set_pricing_model",
            classification=classification,
            model_classification=_matrix_cls,
            manual_classification=_manual,
            triggered_by=f"{_by}_override" if _is_override else _by,
        )
        if _is_override:
            print(f"[learn] HUMAN OVERRIDE on {svc_num}: matrix={_matrix_cls} human={classification}")
    except Exception:
        pass

    return r


@tool
def bulk_adjust(adjustment_id: int, trip_ids: list[int], reason: str = "Increase in occupancy",
                seat_types: list[str] = None) -> str:
    """Apply percentage fare adjustment to trips.
    adjustment_id = PERCENTAGE of increase on base fare.
    e.g. adjustment_id=10 → all fares × 1.10 (10% higher than base).
    adjustment_id=0 → reset to base fare (no adjustment).
    To increase by 5%: pass adjustment_id=current+5. To decrease: current-5.
    Use get_fare_tier() to read current percentage first.
    trip_ids: list of int trip IDs from list_services().
    seat_types: list of 'seater', 'singleSleeper', 'sharedSleeper' — defaults to all."""
    # Same tier scale as global_fare_adjustment's target_tier clamp [1, 10] — 0 also
    # allowed here since bulk_adjust's own contract treats 0 as "reset to base fare".
    safe_adj = max(0, min(10, int(adjustment_id)))
    if safe_adj != int(adjustment_id):
        print(f"[guardrail] bulk_adjust adjustment_id {adjustment_id} clamped to {safe_adj} (range=0-10)")
    c = get_client()
    st = seat_types or ["seater", "singleSleeper", "sharedSleeper"]
    # Capture prev tier for each trip (for undo)
    for tid in trip_ids:
        try:
            prev_tier = c.get_fare_tier(int(tid))
            trips = c.list_services()
            svc_num = next((t.get("service_number", str(tid)) for t in trips
                            if t.get("trip_id") == int(tid)), str(tid))
            _record_for_undo(int(tid), "bulk_adjust", {"prev_tier": prev_tier}, svc_num)
        except Exception:
            pass
    r = c.bulk_adjust(safe_adj, [int(t) for t in trip_ids],
                      reason=reason, seat_types=st)
    _audit("bulk_adjust", {"adjustment_id": safe_adj, "trip_ids": trip_ids, "reason": reason}, r)
    return r


@tool
def static_fare(trip_id: str, seat_ids: list[int], fare: str,
                reason: str = "Window seats") -> str:
    """Set exact fare on specific seat IDs for a trip.
    fare: integer fare amount as string e.g. "399".
    reason: window seats / non - window seats / last row seats / female seats / increase in occupancy"""
    tid = int(trip_id)
    safe_fare = clamp_fare(int(float(fare)))
    if safe_fare != int(fare):
        print(f"[guardrail] fare {fare} clamped to {safe_fare} (floor={FARE_FLOOR}, ceil={FARE_CEILING})")
    c = get_client()
    # Capture current fares for specified seats (for undo)
    try:
        all_fares = c.read_seat_fares(tid)
        prev_fares = {str(s): all_fares.get(str(s), all_fares.get(int(s), safe_fare))
                      for s in seat_ids}
        trips = c.list_services()
        svc_num = next((t.get("service_number", str(tid)) for t in trips
                        if t.get("trip_id") == tid), str(tid))
        _record_for_undo(tid, "static_fare", {"prev_fares": prev_fares}, svc_num)
    except Exception:
        pass
    r = c.static_fare(tid, [int(s) for s in seat_ids], safe_fare, reason=reason)
    mark_repriced(tid)
    _audit("static_fare", {"trip_id": tid, "seats": seat_ids, "fare": safe_fare, "reason": reason}, r)
    return r


@tool
def global_fare_adjustment(delta: int, services: list[str] = None,
                            reason: str = "Increase in occupancy",
                            seat_types: list[str] = None) -> str:
    """Apply bulk fare percentage adjustment (+/-) to multiple trips.
    delta = percentage points to add/subtract from current adjustment.
    e.g. delta=10 → add 10% to current fare adjustment.
    services=None means ALL trips from last search. seat_types=None means all seat types."""
    c = get_client()
    # Ensure fresh data — re-search if trips list is empty
    trips = c.list_services()
    if not trips:
        dsrc, ddst = _route()
        c.search_services(dsrc, ddst)
        trips = c.list_services()
    if services:
        svc_lower = [str(s).lower() for s in services]
        trips = [t for t in trips
                 if any(s in t["service_number"].lower() for s in svc_lower)]
    trip_ids = [t["trip_id"] for t in trips if t.get("trip_id")]
    if not trip_ids:
        return "no matching trips found"
    # adj_id IS the target tier level (absolute, not relative).
    # Read current tier per trip and move by delta tiers.
    # delta > 0 → increase tier, delta < 0 → decrease tier.
    # Clamp tier to [1, 10].
    reason_final = reason if reason != "Increase in occupancy" else (
        "increase in occupancy" if delta >= 0 else "decrease in occupancy"
    )
    st = seat_types or ["seater", "singleSleeper", "sharedSleeper"]
    results = []
    for tid in trip_ids:
        current_tier = c.get_fare_tier(tid)
        target_tier = max(1, min(10, current_tier + delta))
        r = c.bulk_adjust(target_tier, [tid], reason=reason_final, seat_types=st)
        results.append(r)
    r = "; ".join(results)
    direction = f"+{delta}" if delta >= 0 else str(delta)
    _audit("global_fare_adjustment", {"delta": delta, "services": services, "reason": reason_final}, r)
    return f"fare adjustment {direction} applied to {len(trip_ids)} trips"


@tool
def global_pricing_model(model: str, classification: str = "",
                          services: list[str] = None) -> str:
    """Set Pricing Model + Classification on multiple trips.
    services=None means apply to ALL trips from last search."""
    c = get_client()
    # Ensure fresh data
    trips = c.list_services()
    if not trips:
        dsrc, ddst = _route()
        c.search_services(dsrc, ddst)
        trips = c.list_services()
    if services:
        svc_lower = [str(s).lower() for s in services]
        trips = [t for t in trips
                 if any(s in t["service_number"].lower() for s in svc_lower)]
    results = []
    for t in trips:
        tid = t.get("trip_id")
        curr_cls = t.get("classification", "")
        if tid:
            # Idempotency: skip if already correct
            if classification and curr_cls:
                from pricing_rules import needs_reclassification
                if not needs_reclassification(curr_cls, classification):
                    results.append(f"skip {tid}: already {curr_cls}")
                    continue
            r = c.set_pricing_model(int(tid), model=model, classification=classification)
            results.append(r)
    combined = f"updated {len(results)} trips"
    _audit("global_pricing_model", {"model": model, "classification": classification,
                                    "services": services}, combined)
    return combined


# ── TOOL LIST ────────────────────────────────────────────────────────────────

@tool
def reset_static_fare(trip_id: str) -> str:
    """Remove all static fares from a trip — equivalent to portal Reset button.
    Calls POST /trips/{trip_id}/reset_fare_update with all seat IDs."""
    c = get_client()
    return c.reset_static_fare(int(trip_id))


TOOLS = [
    search_services, list_services, get_default_route, set_default_route,
    read_seat_fares, get_seat_layout, get_trip_fares, get_fare_history,
    set_pricing_model, bulk_adjust, static_fare, reset_static_fare,
    global_fare_adjustment, global_pricing_model,
    get_booking_velocity, get_recent_outcomes, remember, recall,
    get_last_boarding_time, get_boarding_points, get_revenue_metrics,
    query_database,
]

# Lean tool set for autoloop/basic pricing — fewer tokens per LLM call
PRICING_TOOLS = [
    search_services,        # get trip IDs
    list_services,          # get service data
    set_pricing_model,      # set classification + model
    static_fare,            # set static fares
    bulk_adjust,            # % fare adjustment
    reset_static_fare,      # clear static fares
    global_pricing_model,   # batch set all services
    query_database,         # analytics / history
    get_pricing_alerts,     # alerts from sales dashboard
    call_mcp_tool,          # call any MCP tool on dashboard.example-portal.com
]
