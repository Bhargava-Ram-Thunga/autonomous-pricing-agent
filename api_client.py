"""PricingCo Admin API client — replaces Playwright portal automation.
Base URL: https://api-stage.example-portal.com/admin
Auth: email/password → access_token in Set-Cookie header.

CACHE STRATEGY:
  - Trips list: cached per (source, destination, date). TTL = 5 min.
  - Seat fares: cached per trip_id. TTL = 2 min.
  - Write actions (pricing change) → invalidate affected trip cache immediately.
  - Explicit refresh: call search_services(refresh=True).
"""
import os
import time
import requests
from datetime import date, datetime
from typing import Optional

BASE_URL = os.environ.get("API_BASE_URL", "https://api-stage.example-portal.com/admin")

TRIPS_CACHE_TTL = 300   # 5 min — trips list
FARES_CACHE_TTL = 120   # 2 min — seat fares per trip

# Classification name → API value mapping
CLASSIFICATION_MAP = {
    "super low":    "Super_Low",
    "low":          "Low",
    "medium":       "Medium",
    "high":         "High",
    "super high":   "Super_High",
    "ultra high":   "Ultra_High",
    "special high": "Special_High",
    "festive":      "Festive",
}

# Pricing model name → API value mapping
MODEL_MAP = {
    "automation v1": "Automation_v1",
    "automation v2": "Automation_v2",
    "automation v3": "Automation_v3",
    "automation v4": "Automation_v4",
    "model v1":      "Model_v1",
    "model v2":      "Model_v2",
    "sciative":      "Sciative",
}

# Reason ID mapping for fare adjustments
REASON_MAP = {
    "increase in occupancy": 1,
    "decrease in occupancy": 2,
    "window seats":          2,
    "non - window seats":    3,
    "last row seats":        4,
    "female seats":          5,
}
DEFAULT_REASON_ID = 1


class PortalAPIClient:
    """HTTP client for PricingCo admin API with built-in cache."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._token: str | None = None
        self._logged_in = False

        # Cache store: key → (data, fetched_at_ts)
        self._cache: dict[str, tuple] = {}

        # Last searched route — used as fallback for seat endpoint params
        self._last_source: str = os.environ.get("DEFAULT_SOURCE", "BANGALORE")
        self._last_dest: str = os.environ.get("DEFAULT_DEST", "TIRUPATI")

    def _cache_get(self, key: str, ttl: int):
        """Return cached value if still fresh, else None."""
        entry = self._cache.get(key)
        if entry and (time.time() - entry[1]) < ttl:
            return entry[0]
        return None

    def _cache_set(self, key: str, data):
        self._cache[key] = (data, time.time())

    def _cache_invalidate(self, trip_id: int | None = None):
        """Invalidate trip-specific or all cache entries after a write."""
        if trip_id:
            keys_to_del = [k for k in self._cache if str(trip_id) in k]
        else:
            keys_to_del = list(self._cache.keys())
        for k in keys_to_del:
            del self._cache[k]
        if keys_to_del:
            print(f"[cache] invalidated {len(keys_to_del)} entries")

    # ── AUTH ────────────────────────────────────────────────────────────────

    def login(self) -> str:
        username = os.environ["PORTAL_USER"]
        password = os.environ["PORTAL_PASS"]
        resp = self.session.post(f"{BASE_URL}/auth/login", json={
            "email": username,
            "password": password,
            "deviceId": "pricing-agent",
        })
        resp.raise_for_status()
        self._store_tokens(resp)
        print(f"[api] logged in as {username}")
        return "logged in"

    def _refresh(self) -> bool:
        """Use refresh_token cookie to get new access_token.
        Returns True on success, False if refresh token expired/invalid.
        """
        try:
            resp = self.session.get(f"{BASE_URL}/auth/refresh-token")
            if resp.status_code == 200:
                stored = self._store_tokens(resp)
                if stored:
                    print("[api] token refreshed")
                    return True
        except Exception:
            pass
        return False

    def _store_tokens(self, resp) -> bool:
        """Extract access_token from response cookies or body. Returns True if found."""
        token = None
        for cookie in resp.cookies:
            if cookie.name == "access_token":
                token = cookie.value
                break
        if not token:
            try:
                data = resp.json()
                token = data.get("access_token") or data.get("token")
            except Exception:
                pass
        if not token:
            return False
        self._token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self._logged_in = True
        return True

    def _reauth(self):
        """On 401: try refresh first, fall back to full login."""
        if not self._refresh():
            print("[api] refresh failed — full re-login")
            self.login()

    def ensure_logged_in(self):
        if not self._logged_in:
            self.login()

    def _get(self, path: str, **params) -> dict | list:
        self.ensure_logged_in()
        resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        if resp.status_code == 401:
            self._reauth()
            resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        resp.raise_for_status()
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    def _post(self, path: str, body: dict) -> dict | list:
        self.ensure_logged_in()
        resp = self.session.post(f"{BASE_URL}{path}", json=body, timeout=30)
        if resp.status_code == 401:
            self._reauth()
            resp = self.session.post(f"{BASE_URL}{path}", json=body, timeout=30)
        resp.raise_for_status()
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    def _patch(self, path: str, body: dict) -> dict | list:
        self.ensure_logged_in()
        resp = self.session.patch(f"{BASE_URL}{path}", json=body, timeout=30)
        if resp.status_code == 401:
            self._reauth()
            resp = self.session.patch(f"{BASE_URL}{path}", json=body, timeout=30)
        resp.raise_for_status()
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    # ── SERVICES & TRIPS ────────────────────────────────────────────────────

    def search_services(self, source: str, destination: str,
                        journey_date: Optional[date] = None,
                        refresh: bool = False) -> str:
        """Search trips for a route and date. Stores results internally."""
        jd = (journey_date or date.today()).isoformat()
        src_id = _station_id(source)
        dst_id = _station_id(destination)
        cache_key = f"trips:{src_id}:{dst_id}:{jd}"

        if not refresh:
            cached = self._cache_get(cache_key, TRIPS_CACHE_TTL)
            if cached is not None:
                self._trips = cached
                print(f"[cache] trips hit — {len(self._trips)} trips on {jd}")
                return f"found {len(self._trips)} trips (cached)"

        data = self._get("/services/trips",
                         journeyDate=jd, sourceId=src_id, destinationId=dst_id)
        self._trips = data if isinstance(data, list) else data.get("data", [])
        self._cache_set(cache_key, self._trips)
        # Track last searched route for seat endpoint fallback
        self._last_source = source
        self._last_dest = destination
        print(f"[api] found {len(self._trips)} trips on {jd}")
        return f"found {len(self._trips)} trips"

    def list_services(self) -> list[dict]:
        """Return standardised service list from last search."""
        if not hasattr(self, "_trips"):
            return []
        result = []
        for t in self._trips:
            svc_num = t.get("serviceNumber") or t.get("service_number", "")
            trip_id = t.get("id") or t.get("tripId")
            booked = t.get("ticketsBooked") or t.get("bookedSeats") or t.get("booked") or 0
            cls = t.get("fareClassification") or t.get("classification") or ""
            model = t.get("pricingModel") or ""
            # Departure datetime — try common field names
            dep = (t.get("departureTime") or t.get("departure_time")
                   or t.get("boardingTime") or t.get("scheduledDeparture")
                   or t.get("journeyStartTime") or "")
            # Convert UTC departure to IST (UTC+5:30) for display
            dep_display = str(dep) if dep else ""
            if dep_display:
                try:
                    from datetime import datetime as _ddt, timezone as _tz, timedelta as _tdelta
                    import re as _re2
                    _IST = _tz(_tdelta(hours=5, minutes=30))
                    _s = dep_display.strip()
                    # Normalise fractional seconds
                    _s = _re2.sub(r'(\.\d{1,3})\d*', r'\g<1>', _s)
                    if _s.endswith("Z"):
                        _s = _s[:-1] + "+00:00"
                    _aware = _ddt.fromisoformat(_s)
                    if _aware.tzinfo is not None:
                        dep_display = _aware.astimezone(_IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")
                except Exception:
                    pass  # keep original if parse fails
            # Active status — portal shows a toggle; only active trips should be priced
            is_active = (t.get("isActive") if t.get("isActive") is not None
                         else t.get("active") if t.get("active") is not None
                         else t.get("status") if isinstance(t.get("status"), bool)
                         else (str(t.get("status", "active")).lower() not in ("inactive", "disabled", "false", "0")))
            total_seats = int(t.get("totalSeats") or t.get("total_seats") or 45)
            result.append({
                "service_number": svc_num,
                "trip_id": trip_id,
                "booked": int(booked),
                "total_seats": total_seats,
                "classification": cls,
                "model": model,
                "range": f"{t.get('minFare','')} - {t.get('maxFare','')}" if t.get("minFare") else "",
                "departure_time": dep_display,
                "is_active": bool(is_active),
            })
        return result

    def get_trip_id(self, service_number: str) -> int:
        """Resolve service number to trip ID."""
        for t in getattr(self, "_trips", []):
            sn = t.get("serviceNumber") or t.get("service_number", "")
            if service_number.lower() in sn.lower() or sn.lower() in service_number.lower():
                return t.get("id") or t.get("tripId")
        raise RuntimeError(f"Trip not found for service {service_number}. Call search_services first.")

    def read_seat_fares(self, trip_id: int) -> dict[str, int]:
        """Return {seat_number: fare} for a trip."""
        cache_key = f"fares:{trip_id}"
        cached = self._cache_get(cache_key, FARES_CACHE_TTL)
        if cached is not None:
            print(f"[cache] fares hit — trip {trip_id}")
            return cached

        # Try without station params — bare endpoint works on most API versions
        # If 400/empty, fall back with source_id/destination_id query params
        seats = []
        try:
            data = self._get(f"/trips/{trip_id}/seats")
            seats = data.get("seats") or (data if isinstance(data, list) else [])
        except Exception:
            pass
        if not seats:
            try:
                src_id = _station_id(self._last_source)
                dst_id = _station_id(self._last_dest)
                data = self._get(f"/trips/{trip_id}/seats",
                                 source_id=src_id, destination_id=dst_id)
                seats = data.get("seats") or (data if isinstance(data, list) else [])
            except Exception:
                pass
        result = {}
        for s in seats:
            num = str(s.get("seatNumber") or s.get("seat_number") or s.get("id", ""))
            fare = s.get("totalFare") or s.get("fare") or 0
            if num:
                result[num] = int(float(fare))
        self._cache_set(cache_key, result)
        return result

    def get_seat_layout(self, trip_id: int) -> list[dict]:
        """Return full seat layout with category classification.
        Each entry: {id, name, type, category, fare, occupied, blocked, has_static_fare, x, y}
        category = 'window' | 'non_window' | 'last_row'
        Use 'id' (int) with static_fare, not 'name'.

        Layout logic (seater 2+2 bus):
          y = min or max across non-last-row seats → window
          y = inner values → non_window
          x = max across all seats → last_row (overrides window/non_window)
        """
        cache_key = f"layout:{trip_id}"
        cached = self._cache_get(cache_key, FARES_CACHE_TTL)
        if cached is not None:
            return cached

        # Fetch seats — try bare first, fallback with station params
        seats = []
        try:
            data = self._get(f"/trips/{trip_id}/seats")
            seats = data.get("seats") or (data if isinstance(data, list) else [])
        except Exception:
            pass
        if not seats:
            try:
                src_id = _station_id(self._last_source)
                dst_id = _station_id(self._last_dest)
                data = self._get(f"/trips/{trip_id}/seats",
                                 source_id=src_id, destination_id=dst_id)
                seats = data.get("seats") or (data if isinstance(data, list) else [])
            except Exception:
                pass

        non_dummy = [s for s in seats if not s.get("isDummy")]
        dummy_seats = [s for s in seats if s.get("isDummy")]
        if not non_dummy:
            return []

        all_x = [s.get("x", 0) for s in non_dummy]
        max_x = max(all_x)

        # Detect bus type: sleeper if ANY seat has "sleeper" in seatType
        # API returns "Sleeper", "Shared Sleeper" (with space, mixed case)
        is_sleeper = any("sleeper" in s.get("seatType", "").lower() for s in non_dummy)

        if is_sleeper:
            # Sleeper bus: category from seatType
            # "Sleeper" / "singleSleeper"  = upper berth = premium → "window" tier
            # "Shared Sleeper" / "sharedSleeper" = lower berth = standard → "non_window"
            # "Seater" on sleeper bus = last-row seats → "last_row" if at max_x else "non_window"
            def _sleeper_cat(s):
                st = s.get("seatType", "").lower()
                sx = s.get("x", 0)
                if sx == max_x:
                    return "last_row"
                if "shared" in st:
                    return "non_window"   # Shared Sleeper = lower berth = standard
                if "sleeper" in st:
                    return "window"       # Sleeper (single/upper) = premium
                return "non_window"       # Seater on sleeper bus = non_window
        else:
            # Seater bus (2+2 layout): window = edge Y rows
            # Y=5 (single extra last-row seat) is NOT a regular row.
            # Determine regular rows = Y values that appear in > 1 non-last-row seat.
            from collections import Counter as _C
            main_seats = [s for s in non_dummy if s.get("x", 0) != max_x]
            y_counts = _C(s.get("y", 0) for s in main_seats)
            regular_ys = sorted(y for y, cnt in y_counts.items() if cnt > 1)
            window_ys = {regular_ys[0], regular_ys[-1]} if len(regular_ys) >= 2 else set()

        result = []
        for s in non_dummy:
            fare_raw = s.get("totalFare") or 0
            if isinstance(fare_raw, dict):
                fare_raw = fare_raw.get("Base Fare", 0)
            sx, sy = s.get("x", 0), s.get("y", 0)

            if is_sleeper:
                category = _sleeper_cat(s)
            elif sx == max_x:
                category = "last_row"
            elif sy in window_ys:
                category = "window"
            else:
                category = "non_window"

            result.append({
                "id": s.get("id"),
                "name": s.get("seatName") or s.get("seatNumber") or "",
                "type": s.get("seatType", ""),
                "category": category,
                "fare": int(float(fare_raw)),
                "occupied": bool(s.get("isOccupied")),
                "blocked": bool(s.get("isBlocked")),
                "has_static_fare": bool(s.get("hasStaticFare")),
                "is_dummy": False,
                "x": sx,
                "y": sy,
            })

        # Include dummy seats using same position-based category logic as non-dummy
        for s in dummy_seats:
            fare_raw = s.get("totalFare") or 0
            if isinstance(fare_raw, dict):
                fare_raw = fare_raw.get("Base Fare", 0)
            sx, sy = s.get("x", 0), s.get("y", 0)
            if is_sleeper:
                category = _sleeper_cat(s)
            elif sx == max_x:
                category = "last_row"
            elif sy in window_ys:
                category = "window"
            else:
                category = "non_window"
            result.append({
                "id": s.get("id"),
                "name": s.get("seatName") or s.get("seatNumber") or "",
                "type": s.get("seatType", ""),
                "category": category,
                "fare": int(float(fare_raw)),
                "occupied": bool(s.get("isOccupied")),
                "blocked": bool(s.get("isBlocked")),
                "has_static_fare": bool(s.get("hasStaticFare")),
                "is_dummy": True,
                "x": sx,
                "y": sy,
            })

        self._cache_set(cache_key, result)
        return result

    def get_trip_fares(self, trip_id: int) -> dict:
        """Get fare adjustment info for a trip."""
        return self._get(f"/trips/{trip_id}/fare_adjustment")

    # ── PRICING ACTIONS ─────────────────────────────────────────────────────

    def set_pricing_model(self, trip_id: int, model: str = "",
                          classification: str = "") -> str:
        """Set pricing model and/or classification on a trip.
        API requires BOTH pricingModel + fareClassification in body.
        If one is missing, fetch current value from trip list to fill it in."""
        body = {}
        if classification:
            key = classification.lower()
            body["fareClassification"] = CLASSIFICATION_MAP.get(key, classification)
        if model:
            key = model.lower()
            body["pricingModel"] = MODEL_MAP.get(key, model)
        if not body:
            return "nothing to set"
        # API requires both fields — fill missing one from current trip data
        if "pricingModel" not in body or "fareClassification" not in body:
            try:
                trips = self.list_services()
                curr = next((t for t in trips if t.get("trip_id") == trip_id), None)
                if curr:
                    if "pricingModel" not in body and curr.get("model"):
                        m_key = curr["model"].lower().replace("_", " ")
                        body["pricingModel"] = MODEL_MAP.get(m_key, curr["model"])
                    if "fareClassification" not in body and curr.get("classification"):
                        c_key = curr["classification"].lower().replace("_", " ")
                        body["fareClassification"] = CLASSIFICATION_MAP.get(c_key, curr["classification"])
            except Exception:
                pass
        # Fallback: if still missing, use safe defaults
        if "pricingModel" not in body:
            body["pricingModel"] = "Automation_v4"   # always default to Automation v4
        if "fareClassification" not in body:
            # Use current classification if available — don't override with arbitrary default
            try:
                trips = self.list_services()
                curr_trip = next((t for t in trips if t.get("trip_id") == int(list(body.keys())[0] if body else 0)), None)
                body["fareClassification"] = curr_trip.get("classification", "Low") if curr_trip else "Low"
            except Exception:
                body["fareClassification"] = "Low"
        self._patch(f"/trips/{trip_id}/updatePriceClassification", body)
        self._cache_invalidate(trip_id)
        parts = []
        if "fareClassification" in body:
            parts.append(f"classification={body['fareClassification']}")
        if "pricingModel" in body:
            parts.append(f"model={body['pricingModel']}")
        return f"updated {', '.join(parts)} on trip {trip_id}"

    def get_fare_tier(self, trip_id: int) -> int:
        """Return current seater fare adjustment tier for a trip (0 = no adjustment)."""
        try:
            data = self._get(f"/trips/{trip_id}/fare_adjustment")
            return int(data.get("seater", 0))
        except Exception:
            return 0

    def bulk_adjust(self, adjustment_id: int, trip_ids: list[int],
                    reason: str = "Increase in occupancy",
                    seat_types: list[str] = None) -> str:
        """Apply a bulk fare adjustment to trips.
        adjustment_id = PERCENTAGE increase applied to base fare.
        e.g. adjustment_id=10 → fare × 1.10 (10% increase).
        adjustment_id=0 → no adjustment (reset to base).
        Use get_fare_tier() to read current percentage before adjusting."""
        st = seat_types or ["seater", "singleSleeper", "sharedSleeper"]
        reason_id = REASON_MAP.get(reason.lower(), DEFAULT_REASON_ID)
        results = []
        for tid in trip_ids:
            current = self.get_fare_tier(tid)
            self._post(f"/trips/fare_adjustment/{adjustment_id}", {
                "tripIds": [tid],
                "seatType": st,
                "reasonId": reason_id,
            })
            self._cache_invalidate(tid)
            direction = "increase" if adjustment_id > current else "decrease"
            results.append(f"trip {tid}: tier {current}->{adjustment_id} ({direction})")
        return "; ".join(results) if results else "no trips to adjust"

    def static_fare(self, trip_id: int, seat_ids: list[int],
                    fare: int, reason: str = "Window seats") -> str:
        """Set exact fare on specific seats."""
        reason_id = REASON_MAP.get(reason.lower(), DEFAULT_REASON_ID)
        self._post(f"/trips/{trip_id}/fare_update", {
            "seats": seat_ids,
            "fare": fare,
            "reasonId": reason_id,
        })
        self._cache_invalidate(trip_id)
        return f"set ₹{fare} on {len(seat_ids)} seats (trip {trip_id})"

    def get_revenue_metrics(self, trip_id: int) -> dict:
        """Calculate Revenue, ASP, EPK for a trip.
        Revenue = sum of fares on occupied seats.
        ASP = Revenue / booked seats.
        EPK = Revenue / route distance KM.
        """
        layout = self.get_seat_layout(trip_id)
        fares  = self.read_seat_fares(trip_id)
        occupied  = [s for s in layout if s.get("occupied")]
        available = [s for s in layout if not s.get("occupied") and not s.get("blocked") and not s.get("is_dummy")]
        revenue = 0
        for seat in occupied:
            sid = str(seat.get("id",""))
            sname = str(seat.get("name",""))
            fare = fares.get(sid) or fares.get(sname) or seat.get("fare") or 0
            revenue += int(float(fare))
        unsold_revenue = 0
        for seat in available:
            sid = str(seat.get("id",""))
            sname = str(seat.get("name",""))
            fare = fares.get(sid) or fares.get(sname) or seat.get("fare") or 0
            unsold_revenue += int(float(fare))
        booked   = len(occupied)
        unsold   = len(available)
        asp      = round(revenue / booked, 2) if booked else 0
        unsold_asp = round(unsold_revenue / unsold, 2) if unsold else 0
        potential_revenue = revenue + unsold_revenue
        dist = get_route_distance_km(self._last_source, self._last_dest)
        epk  = round(revenue / dist, 2) if dist else 0
        potential_epk = round(potential_revenue / dist, 2) if dist else 0
        return {
            "trip_id":           trip_id,
            "booked_seats":      booked,
            "available_seats":   unsold,
            "revenue":           revenue,
            "asp":               asp,
            "unsold_asp":        unsold_asp,
            "unsold_revenue":    unsold_revenue,
            "potential_revenue": potential_revenue,
            "route_km":          dist,
            "epk":               epk,
            "potential_epk":     potential_epk,
        }

    def get_boarding_points(self, trip_id: int, station_id: int = None) -> list:
        """Return boarding points for a trip ordered by scheduledTime.
        station_id defaults to last searched source station."""
        sid = station_id or _station_id(self._last_source)
        data = self._get(f"/trips/{trip_id}/boarding", stationId=sid)
        points = data if isinstance(data, list) else data.get("data", [])
        # Sort by scheduledTime ascending
        def _t(p):
            return p.get("scheduledTime") or p.get("currentTime") or ""
        return sorted(points, key=_t)

    def get_last_boarding_time(self, trip_id: int, station_id: int = None) -> dict | None:
        """Return last boarding point {name, scheduledTime (IST), station} for a trip."""
        points = self.get_boarding_points(trip_id, station_id)
        if not points:
            return None
        last = points[-1]
        # Convert scheduledTime UTC → IST
        ist_str = ""
        raw_t = last.get("scheduledTime") or last.get("currentTime") or ""
        if raw_t:
            try:
                from datetime import datetime as _ddt, timezone as _tz, timedelta as _tdelta
                import re as _re3
                _IST = _tz(_tdelta(hours=5, minutes=30))
                _s = _re3.sub(r'(\.\d{1,3})\d*', r'\g<1>', raw_t.strip())
                if _s.endswith("Z"):
                    _s = _s[:-1] + "+00:00"
                ist_str = _ddt.fromisoformat(_s).astimezone(_IST).strftime("%I:%M %p")
            except Exception:
                ist_str = raw_t
        return {
            "name": last.get("name", ""),
            "station": last.get("station", ""),
            "time_ist": ist_str,
            "raw": raw_t,
        }

    def reset_static_fare(self, trip_id: int) -> str:
        """Remove all static fares from a trip (portal Reset button equivalent).
        Calls POST /trips/{trip_id}/reset_fare_update with all seat IDs in body."""
        # Fetch layout to get all seat IDs
        layout = self.get_seat_layout(trip_id)
        seat_ids = [s["id"] for s in layout if s.get("id") is not None]
        if not seat_ids:
            return f"no seats found for trip {trip_id}"
        self._post(f"/trips/{trip_id}/reset_fare_update", {"seats": seat_ids})
        self._cache_invalidate(trip_id)
        return f"static fares cleared on trip {trip_id} ({len(seat_ids)} seats)"

    def get_fare_history(self, trip_id: int) -> list:
        """Return fare change history for a trip."""
        data = self._get(f"/trips/{trip_id}/fare_history")
        return data if isinstance(data, list) else data.get("data", [])

    def get_pricing_layout(self, service_id: int,
                           journey_date: Optional[date] = None) -> dict:
        """Get full pricing seat layout for a service on a date."""
        jd = (journey_date or date.today()).isoformat()
        return self._get("/trips/pricing-seat-layout",
                         serviceId=service_id, journeyDate=jd)


# ── STATION ID LOOKUP ────────────────────────────────────────────────────────

# Route distances in KM — used for EPK calculation
_ROUTE_DISTANCES = {
    ("bangalore",  "tirupati"):    280,
    ("bangalore",  "hyderabad"):   570,
    ("bangalore",  "vijayawada"):  670,
    ("bangalore",  "chennai"):     346,
    ("bangalore",  "visakhapatnam"): 1050,
    ("hyderabad",  "vijayawada"):  275,
    ("hyderabad",  "tirupati"):    550,
    ("hyderabad",  "chennai"):     630,
}

def get_route_distance_km(source: str, destination: str) -> int:
    """Return route distance in KM. Returns 0 if unknown."""
    src = source.lower().strip()
    dst = destination.lower().strip()
    return _ROUTE_DISTANCES.get((src, dst)) or _ROUTE_DISTANCES.get((dst, src)) or 0


_STATION_IDS = {
    "bangalore":   7,
    "bengaluru":   7,
    "blr":         7,
    "tirupati":    12,
    "tpt":         12,
    "hyderabad":   3,
    "hyd":         3,
    "vijayawada":  5,
    "vjy":         5,
    "vja":         5,
    "vijaya":      5,
    "chennai":     6,
    "chn":         6,
    "visakhapatnam": 58,
    "vizag":       58,
    "eluru":       99,
    "mysore":      926,
    "pondicherry": 413,
    "erode":       418,
}


def _station_id(name: str) -> int:
    key = name.lower().strip()
    sid = _STATION_IDS.get(key)
    if sid:
        return sid
    # Partial match
    for k, v in _STATION_IDS.items():
        if k in key or key in k:
            return v
    raise RuntimeError(f"Unknown station: '{name}'. Add to _STATION_IDS in api_client.py")


# ── SINGLETON ─────────────────────────────────────────────────────────────────

_client: PortalAPIClient | None = None


def get_client() -> PortalAPIClient:
    global _client
    if _client is None:
        _client = PortalAPIClient()
        _client.login()
    return _client
