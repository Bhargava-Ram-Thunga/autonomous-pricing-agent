"""Read-only pricing portal data from Postgres.
Replaces pricing portal API read calls with direct Postgres queries.
Write operations (classification, model, fare adjustment, static fare) still use API.
"""
import os
from datetime import date, datetime
from psycopg import Connection
from psycopg.rows import dict_row

_conn: Connection | None = None


def _get_conn() -> Connection:
    global _conn
    try:
        if _conn is not None and not _conn.closed:
            # Ping to verify connection is alive
            with _conn.cursor() as _c:
                _c.execute("SELECT 1")
            return _conn
    except Exception:
        _conn = None
    uri = os.environ.get("POSTGRES_URI", "")
    if not uri:
        raise RuntimeError("POSTGRES_URI not set")
    _conn = Connection.connect(uri, autocommit=True, prepare_threshold=0, row_factory=dict_row)
    return _conn


# ── TRIPS / SERVICES ──────────────────────────────────────────────────────────

def get_trips(source_id: int, destination_id: int, journey_date: date) -> list[dict]:
    """Return trips for a route + date. Mirrors /services/trips API."""
    with _get_conn().cursor() as cur:
        cur.execute("""
            SELECT
                t.id                  AS trip_id,
                t."serviceNumber"     AS service_number,
                t."serviceName"       AS service_name,
                t."journeyDate"       AS journey_date,
                t."fareClassification"::text AS classification,
                t."pricingModel"::text       AS pricing_model,
                t.active,
                (SELECT COUNT(*) FROM public."TripSeats" ts2
                 WHERE ts2."tripId" = t.id AND ts2.active = true
                   AND ts2."sourceId" = %s AND ts2."destinationId" = %s
                   AND ts2.available = false)  AS booked,
                t."totalRevenue"      AS total_revenue,
                t.asp,
                t."fareAdjustment"    AS fare_adjustment,
                s."vehicleTypeId"     AS vehicle_type_id,
                (SELECT COUNT(*) FROM public."TripSeats" ts
                 WHERE ts."tripId" = t.id AND ts.active = true
                   AND ts."sourceId" = %s AND ts."destinationId" = %s) AS total_seats,
                (SELECT MIN(tbp."scheduledTime")
                 FROM public."TripBoardingPoints" tbp
                 WHERE tbp."tripId" = t.id AND tbp.active = true) AS first_boarding,
                (SELECT MAX(tbp."scheduledTime")
                 FROM public."TripBoardingPoints" tbp
                 WHERE tbp."tripId" = t.id AND tbp.active = true) AS last_boarding
            FROM public."Trips" t
            JOIN public."Services" s ON s.id = t."serviceId"
            WHERE t."sourceId" = %s
              AND t."destinationId" = %s
              AND t."journeyDate" = %s
            ORDER BY t."serviceNumber"
        """, (source_id, destination_id, source_id, destination_id,
              source_id, destination_id, journey_date))
        return cur.fetchall()


def get_trip_by_id(trip_id: int) -> dict | None:
    """Return single trip by ID."""
    with _get_conn().cursor() as cur:
        cur.execute("""
            SELECT t.id AS trip_id, t."serviceNumber" AS service_number,
                   t."fareClassification"::text AS classification,
                   t."pricingModel"::text AS pricing_model,
                   t.active, t."totalOccupency" AS booked,
                   t."journeyDate" AS journey_date, t."fareAdjustment" AS fare_adjustment
            FROM public."Trips" t WHERE t.id = %s
        """, (trip_id,))
        return cur.fetchone()


# ── SEATS ─────────────────────────────────────────────────────────────────────

def get_trip_seats(trip_id: int, source_id: int = None, destination_id: int = None) -> list[dict]:
    """Return seat layout + fares for a trip. Mirrors /trips/{id}/seats API.
    Filters by source/destination to get route-specific seats (45 seats per route, not all 135)."""
    # Auto-detect source/dest from the _pg_conn context if not provided
    if source_id is None or destination_id is None:
        try:
            with _get_conn().cursor() as _cur:
                _cur.execute('SELECT "sourceId", "destinationId" FROM public."Trips" WHERE id=%s', (trip_id,))
                _row = _cur.fetchone()
                if _row:
                    source_id = source_id or _row["sourceId"]
                    destination_id = destination_id or _row["destinationId"]
        except Exception:
            pass
    params = [trip_id]
    extra = ""
    if source_id and destination_id:
        extra = 'AND ts."sourceId" = %s AND ts."destinationId" = %s'
        params += [source_id, destination_id]

    with _get_conn().cursor() as cur:
        cur.execute(f"""
            SELECT
                ts.id,
                s.name               AS seat_name,
                ts."seatId"          AS seat_number,
                s."seatType"::text   AS seat_type,
                s."positionX"        AS x,
                s."positionY"        AS y,
                false                AS is_dummy,
                ts.fare              AS total_fare,
                ts.available,
                ts."availablityStatus"::text AS availability_status,
                ts."hasStaticFare"   AS has_static_fare,
                ts."fareAdjustment"  AS fare_adjustment
            FROM public."TripSeats" ts
            JOIN public."Seats" s ON s.id = ts."seatId"
            WHERE ts."tripId" = %s
              AND ts.active = true
              {extra}
            ORDER BY s."positionX", s."positionY"
        """, params)
        return cur.fetchall()


# ── FARE HISTORY ──────────────────────────────────────────────────────────────

def get_fare_history(trip_id: int, limit: int = 50) -> list[dict]:
    """Return fare change history for a trip."""
    with _get_conn().cursor() as cur:
        cur.execute("""
            SELECT h.id, h."tripId" AS trip_id, h."seatId" AS seat_id,
                   h.fare, h."createdAt" AS changed_at,
                   h."pricingModel"::text AS pricing_model
            FROM public."TripSeatFareHistory" h
            WHERE h."tripId" = %s
            ORDER BY h."createdAt" DESC
            LIMIT %s
        """, (trip_id, limit))
        return cur.fetchall()


def get_trip_classification_history(trip_id: int) -> list[dict]:
    """Return classification change history for a trip."""
    with _get_conn().cursor() as cur:
        cur.execute("""
            SELECT id, "tripId" AS trip_id,
                   "fareClassification"::text AS classification,
                   "pricingModel"::text AS pricing_model,
                   "createdAt" AS changed_at
            FROM public."TripClassificationHistory"
            WHERE "tripId" = %s
            ORDER BY "createdAt" DESC
            LIMIT 20
        """, (trip_id,))
        return cur.fetchall()


# ── BOARDING POINTS ───────────────────────────────────────────────────────────

def get_boarding_points(trip_id: int, station_id: int = None) -> list[dict]:
    """Return boarding points for a trip ordered by scheduled time."""
    with _get_conn().cursor() as cur:
        extra = 'AND bp."stationId" = %s' if station_id else ""
        params = [trip_id] + ([station_id] if station_id else [])
        cur.execute(f"""
            SELECT
                tbp."boardingPointId" AS id,
                bp.name,
                bp."stationId"        AS station_id,
                st.name               AS station,
                tbp."scheduledTime"   AS scheduled_time,
                tbp."currentTime"     AS current_time,
                tbp.prime,
                tbp.active
            FROM public."TripBoardingPoints" tbp
            JOIN public."BoardingPoints" bp  ON bp.id  = tbp."boardingPointId"
            JOIN public."Stations"       st  ON st.id  = bp."stationId"
            WHERE tbp."tripId" = %s
              AND tbp.active = true
              {extra}
            ORDER BY tbp."scheduledTime"
        """, params)
        return cur.fetchall()


# ── REVENUE / ASP / EPK ───────────────────────────────────────────────────────

def get_revenue_metrics(trip_id: int, route_km: int = 0) -> dict:
    """Calculate Revenue, ASP, EPK from Postgres seat data."""
    with _get_conn().cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE NOT ts.available)          AS booked_seats,
                COUNT(*) FILTER (WHERE ts.available)              AS available_seats,
                SUM(ts.fare) FILTER (WHERE NOT ts.available)      AS revenue,
                AVG(ts.fare) FILTER (WHERE NOT ts.available)      AS asp,
                AVG(ts.fare) FILTER (WHERE ts.available)          AS unsold_asp
            FROM public."TripSeats" ts
            WHERE ts."tripId" = %s AND ts.active = true
        """, (trip_id,))
        row = cur.fetchone()
        revenue      = float(row["revenue"] or 0)
        booked       = int(row["booked_seats"] or 0)
        available    = int(row["available_seats"] or 0)
        asp          = float(row["asp"] or 0)
        unsold_asp   = float(row["unsold_asp"] or 0)
        epk          = round(revenue / route_km, 2) if route_km else 0
        pot_rev      = revenue + (unsold_asp * available)
        return {
            "trip_id":           trip_id,
            "booked_seats":      booked,
            "available_seats":   available,
            "revenue":           round(revenue, 2),
            "asp":               round(asp, 2),
            "unsold_asp":        round(unsold_asp, 2),
            "potential_revenue": round(pot_rev, 2),
            "route_km":          route_km,
            "epk":               epk,
        }
