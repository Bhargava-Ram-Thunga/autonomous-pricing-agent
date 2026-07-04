"""LangChain Tools — submit to worker thread that owns Portal."""
import os
import json
import re
from datetime import datetime
from pathlib import Path
from langchain_core.tools import tool
from worker import submit, record_bookings, booking_velocity

# Live-configurable default route
import route_config as _rc


def _route() -> tuple[str, str]:
    return _rc.get_route()

CHANGES_LOG = Path("changes.jsonl")
WRITE_TOOLS = {"set_pricing_model", "bulk_adjust", "static_fare",
               "reset_static_fares", "global_fare_adjustment", "global_pricing_model"}


_ACTION_LABELS = {
    "set_pricing_model": lambda a: f"Set pricing → model={a.get('model','')}, class={a.get('classification','')}",
    "bulk_adjust":       lambda a: f"Fare {'increased' if int(a.get('delta',0))>0 else 'decreased'} by ₹{abs(int(a.get('delta',0)))} on all seats",
    "static_fare":       lambda a: f"Fixed fares → seats {a.get('seats',[])} set to ₹{a.get('fare','')}",
    "reset_static_fares":lambda a: "Static fares cleared — pricing model takes over",
    "global_fare_adjustment": lambda a: f"Global fare {'increase' if int(a.get('delta',0))>0 else 'decrease'} ₹{abs(int(a.get('delta',0)))} on {a.get('services','all services')}",
    "global_pricing_model":   lambda a: f"Global pricing → {a.get('classification','')} set on {a.get('services','all services')}",
}


def _audit(tool_name: str, args: dict, result: str):
    if tool_name not in WRITE_TOOLS:
        return
    ts = datetime.now().isoformat(timespec="seconds")
    rec = {"ts": ts, "tool": tool_name, "args": args, "result": result}
    with CHANGES_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

    # Human-readable console log
    label = _ACTION_LABELS.get(tool_name, lambda a: tool_name)(args)
    svc = _LAST_SERVICE.get("name", "unknown service")
    short_svc = svc.split("-")[-1] if "-" in svc else svc
    print(f"[action] {datetime.now().strftime('%H:%M:%S')} | {short_svc} | {label}")

    # Record outcome for learning
    try:
        from state_store import record_outcome
        from worker import _HISTORY
        booked_before = _HISTORY.get(svc, [(0, 0)])[-1][1] if svc else 0
        record_outcome(svc, tool_name, args, booked_before, None)
    except Exception:
        pass


# Tracks last opened service across tools so pricing actions self-recover.
_LAST_SERVICE = {"name": ""}


def _ensure_seats_tab(p):
    """Make sure we're on a service edit page with Seats tab. Auto-recover if not."""
    if "service-management/trips/edit" not in p.page.url:
        if not _LAST_SERVICE["name"]:
            raise RuntimeError("No service opened yet. Call open_service first.")
        p.search_services(*_route())
        p.open_service(_LAST_SERVICE["name"])
    p.open_seats()


def _resolve_service(p, requested: str) -> str:
    """Match requested string to actual service number from current trips list."""
    svcs = p.list_services()
    if not svcs:
        p.search_services(*_route())
        svcs = p.list_services()
    names = [s["service_number"] for s in svcs]
    # Exact
    for n in names:
        if n == requested:
            return n
    # Case-insensitive contains
    req_l = requested.lower()
    for n in names:
        if req_l in n.lower() or n.lower() in req_l:
            return n
    # Last 4 digits
    digits = re.findall(r"\d{3,}", requested)
    if digits:
        for n in names:
            if digits[-1] in n:
                return n
    raise RuntimeError(f"Service '{requested}' not found. Available: {names}")


@tool
def search_services(source: str = "", destination: str = "", journey_date: str = "") -> str:
    """Search trips by source/destination on a date.
    journey_date format YYYY-MM-DD. Defaults: configured route, today.
    For tomorrow pass YYYY-MM-DD of tomorrow."""
    from datetime import date as _d, datetime as _dt
    dsrc, ddst = _route()
    src = source or dsrc
    dst = destination or ddst
    d = None
    if journey_date:
        try:
            d = _dt.strptime(journey_date, "%Y-%m-%d").date()
        except Exception:
            pass
    return submit(lambda p: p.search_services(src, dst, journey_date=d))


@tool
def set_default_route(source: str, destination: str) -> str:
    """Change the live default route (persists across restarts)."""
    return _rc.set_route(source, destination)


@tool
def get_default_route() -> str:
    """Return current default route."""
    src, dst = _route()
    return f"{src} → {dst}"


@tool
def list_services() -> str:
    """JSON list of services from current search results."""
    def _run(p):
        svcs = p.list_services()
        record_bookings(svcs)
        return json.dumps(svcs)
    return submit(_run)


@tool
def get_recent_outcomes(service_number: str = "", limit: int = 10) -> str:
    """Return recent past actions + their booking-delta outcome score.
    Use to learn which adjustments worked. Empty service = all."""
    from state_store import recent_outcomes, evaluate_pending_outcomes
    try:
        evaluate_pending_outcomes(window_min=30)
    except Exception:
        pass
    rows = recent_outcomes(service_number or None, limit)
    # convert datetime to str
    for r in rows:
        if r.get("ts"):
            r["ts"] = r["ts"].isoformat(timespec="seconds")
    return json.dumps(rows, default=str)


@tool
def remember(service_number: str, key: str, value: str) -> str:
    """Persist a note/decision/observation for a service (e.g. 'override_class', 'last_review')."""
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
def get_available_range(service_number: str = "") -> str:
    """Return min/max fare across AVAILABLE (not blocked/occupied) seats only.
    Excludes disabled seats. Requires service open on Seats tab."""
    def _run(p):
        if service_number:
            _ensure_service_open(p, service_number) if False else None
        fares = p.read_seat_fares()
        disabled = p.disabled_seats()
        avail = {s: f for s, f in fares.items() if s not in disabled}
        if not avail:
            return json.dumps({"error": "no available seats"})
        return json.dumps({
            "available_count": len(avail),
            "min": min(avail.values()),
            "max": max(avail.values()),
            "blocked_count": len(disabled),
        })
    # Need helper for service open
    def _open_first(p):
        if service_number:
            if "service-management/trips" not in p.page.url:
                p.search_services(*_route())
            actual = _resolve_service(p, service_number)
            _LAST_SERVICE["name"] = actual
            p.open_service(actual)
            p.open_seats()
        return _run(p)
    return submit(_open_first)


@tool
def get_booking_velocity(service_number: str, window_min: int = 60) -> str:
    """Return booking rate for service over last window_min minutes.
    Returns JSON {booked_now, booked_then, delta, per_hour}. Useful to detect surge demand."""
    return json.dumps(booking_velocity(service_number, int(window_min)))


@tool
def open_service(service_number: str) -> str:
    """Open a service by its service_number. Auto-searches + fuzzy-matches."""
    def _run(p):
        if "service-management/trips" not in p.page.url:
            p.search_services(*_route())
        actual = _resolve_service(p, service_number)
        _LAST_SERVICE["name"] = actual
        r = p.open_service(actual)
        p.open_seats()  # always land on Seats tab
        return f"{r} (resolved '{service_number}' -> '{actual}')"
    return submit(_run)


@tool
def open_seats() -> str:
    """Switch to the Seats tab of the currently open service."""
    return submit(lambda p: p.open_seats())


@tool
def set_pricing_model(model: str = "", classification: str = "") -> str:
    """Change Pricing Model and/or Fare Classification on current service."""
    def _run(p):
        _ensure_seats_tab(p)
        return p.set_pricing_model(model, classification)
    r = submit(_run)
    _audit("set_pricing_model", {"model": model, "classification": classification}, r)
    return r


@tool
def bulk_adjust(delta: int, reason: str = "Increase in occupancy", tier: str = "Seater") -> str:
    """Bus Fare Adjustment: +/- flat amount on all seats."""
    def _run(p):
        _ensure_seats_tab(p)
        return p.bulk_adjust(int(delta), reason=reason, tier=tier)
    r = submit(_run)
    _audit("bulk_adjust", {"delta": delta, "reason": reason, "tier": tier}, r)
    return r


@tool
def static_fare(seats: list, fare: float, reason: str = "Window seats") -> str:
    """Set exact fare on listed seats with a reason. Skips if already matches."""
    def _run(p):
        _ensure_seats_tab(p)
        # Idempotent: check current fares first
        try:
            current = p.read_seat_fares()
            seat_strs = [str(s) for s in seats]
            target = int(float(fare))
            need_apply = [s for s in seat_strs if current.get(s) != target]
            if not need_apply:
                return f"static_fare skip: all {len(seat_strs)} seats already at ₹{target}"
        except Exception:
            pass
        return p.static_fare([str(s) for s in seats], float(fare),
                              reason=reason, only_yellow=False)
    r = submit(_run)
    _audit("static_fare", {"seats": seats, "fare": fare, "reason": reason}, r)
    return r


@tool
def reset_static_fares() -> str:
    """Clear all static fares on current service."""
    def _run(p):
        _ensure_seats_tab(p)
        return p.reset_static_fares()
    r = submit(_run)
    _audit("reset_static_fares", {}, r)
    return r


@tool
def read_seat_fares() -> str:
    """JSON map of {seat_number: fare} from current Seats tab."""
    return submit(lambda p: json.dumps(p.read_seat_fares()))


@tool
def global_fare_adjustment(delta: int, services: list = None, reason: str = "Increase in occupancy",
                            seat_types: list = None) -> str:
    """Apply bulk fare delta to multiple selected services + selected seat types.
    services=None → ALL services. seat_types=None → ALL types (Seater/Solo Sleeper/Shared Sleeper)."""
    def _run(p):
        if "service-management/trips" not in p.page.url:
            p.search_services(*_route())
        svc_list = [str(s) for s in services] if services else None
        st_list = [str(s) for s in seat_types] if seat_types else None
        return p.global_fare_adjustment(int(delta), services=svc_list,
                                         reason=reason, seat_types=st_list)
    r = submit(_run)
    _audit("global_fare_adjustment", {"delta": delta, "services": services,
                                       "reason": reason, "seat_types": seat_types}, r)
    return r


@tool
def global_pricing_model(model: str, classification: str = "", services: list = None) -> str:
    """Set Pricing Model + Classification on multiple selected services via top-right Pricing Model button.
    services=None means apply to ALL."""
    def _run(p):
        if "service-management/trips" not in p.page.url:
            p.search_services(*_route())
        svc_list = [str(s) for s in services] if services else None
        return p.global_pricing_model(model, classification or None, services=svc_list)
    r = submit(_run)
    _audit("global_pricing_model", {"model": model, "classification": classification,
                                     "services": services}, r)
    return r


TOOLS = [
    search_services, list_services, open_service, open_seats,
    set_pricing_model, bulk_adjust, static_fare, reset_static_fares,
    read_seat_fares, global_fare_adjustment, global_pricing_model,
    get_booking_velocity, get_recent_outcomes, remember, recall,
    set_default_route, get_default_route, get_available_range,
]
