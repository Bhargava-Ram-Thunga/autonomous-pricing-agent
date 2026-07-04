"""Pricing rules from official PricingCo matrix (BLR-TPT).

Three dimensions:
  - Day of week (Mon/Tue/Sun=A, Wed/Thu/Sat=B, Fri=C)
  - Seats occupied (0,4,9,13,18,22,26,31,35,40 — lower bound of band)
  - Hours to departure (-2,-1,0,1,2,3,4,6,8,10,12,16,20,24,30,36,42,48,60,72,720)

Each cell: (classification, fare_delta_rupees)
  classification="" → static fares zone (set fixed seat-type fares)
  fare_delta > 0   → apply bulk fare increase on top of classification
"""

# ── FARE GUARDRAILS ──────────────────────────────────────────────────────────
FARE_FLOOR   = 299
FARE_CEILING = 999999  # no upper limit — AI surge can go as high as demand justifies

# ── CLASSIFICATION TIER ORDER ─────────────────────────────────────────────────
TIER_ORDER = [
    "super low", "low", "medium", "high",
    "super high", "ultra high", "special high", "festive",
]

def tier_index(cls: str) -> int:
    n = cls.lower().replace("_", " ").replace("-", " ").strip()
    return TIER_ORDER.index(n) if n in TIER_ORDER else -1

def upgrade_tier(cls: str, steps: int = 1) -> str:
    idx = tier_index(cls)
    if idx < 0:
        return cls
    return TIER_ORDER[min(idx + steps, len(TIER_ORDER) - 1)]


# ── MATRIX DATA ───────────────────────────────────────────────────────────────
# Columns = hours to departure
HOUR_COLS = [-2, -1, 0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 30, 36, 42, 48, 60, 72, 720]

# Rows = seats occupied lower bound
SEAT_THRESHOLDS = [0, 4, 9, 13, 18, 22, 26, 31, 35, 40]

# Shorthand
S   = ("", 0)           # static fares

def _c(cls, d=0):
    return (cls, d)

SL  = _c("super low")
L   = _c("low")
M   = _c("medium")
H   = _c("high")
SH  = _c("super high")
UH  = _c("ultra high")
SpH = _c("special high")
F   = _c("festive")

def _d(cls, delta): return _c(cls, delta)

# ── GROUP A: Mon / Tue / Sun ──────────────────────────────────────────────────
#            -2  -1   0   1   2   3   4   6   8  10  12  16   20  24  30  36  42  48  60  72 720
_A = {
    0:  [S,  S,  S,  S,  S,  S,  S,  S,  S,  S,  S,  SL,  L,  L,  L,  L,  L,  L,  L,  L,  L],
    4:  [S,  S,  S,  S,  S,  S,  S,  S,  S,  S,  SL, _d("super low",10), L, L, L, L, L, L, L, L, L],
    9:  [S,  S,  S,  S,  S,  S,  S,  S,  S,  SL, _d("super low",10), L, _d("low",10), _d("low",10), _d("low",10), _d("low",10), _d("low",10), _d("low",10), _d("low",10), _d("low",10), _d("low",10)],
    13: [S,  S,  S,  S,  S,  S,  S,  S,  SL, _d("super low",10), L, _d("low",10), _d("low",20), _d("low",20), _d("low",20), _d("low",20), _d("low",20), _d("low",20), _d("low",20), _d("low",20), _d("low",20)],
    18: [S,  S,  S,  S,  S,  S,  S,  SL, _d("super low",10), L, _d("low",10), _d("low",20), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10)],
    22: [S,  S,  S,  S,  S,  S,  SL, _d("super low",10), L, _d("low",10), _d("low",20), _d("medium",8), _d("medium",20), _d("medium",20), _d("medium",20), _d("medium",20), _d("medium",20), _d("medium",20), _d("medium",20), _d("medium",20), _d("medium",20)],
    26: [S,  S,  S,  S,  S,  SL, _d("super low",10), L, _d("low",10), _d("low",20), _d("medium",8), _d("medium",12), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10)],
    31: [S,  S,  S,  S,  SL, _d("super low",10), L, _d("low",10), _d("low",20), _d("medium",8), _d("medium",12), _d("high",10), _d("high",20), _d("high",20), _d("high",20), _d("high",20), _d("high",20), _d("high",20), _d("high",20), _d("high",20), _d("high",20)],
    35: [S,  S,  S,  SL, _d("super low",10), L, _d("low",10), _d("low",20), _d("medium",8), _d("medium",12), _d("medium",18), _d("high",15), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10)],
    40: [S,  S,  SL, _d("super low",10), _d("super low",20), _d("low",10), _d("low",20), _d("medium",8), _d("medium",12), _d("medium",18), _d("medium",22), _d("high",20), _d("super high",20), _d("super high",20), _d("super high",20), _d("super high",20), _d("super high",20), _d("super high",20), _d("super high",20), _d("super high",20), _d("super high",20)],
}

# ── GROUP B: Wed / Thu / Sat ──────────────────────────────────────────────────
#            -2  -1   0   1   2   3   4   6   8  10  12  16   20  24  30  36  42  48  60  72 720
_B = {
    0:  [S,  S,  S,  S,  S,  S,  S,  S,  S,  SL, L,  L,  M,  M,  M,  M,  M,  M,  M,  M,  M],
    4:  [S,  S,  S,  S,  S,  S,  S,  S,  SL, L,  _d("low",10), _d("low",10), M, M, M, M, M, M, M, M, M],
    9:  [S,  S,  S,  S,  S,  S,  S,  SL, L,  _d("low",10), M,  M,  _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10), _d("medium",10)],
    13: [S,  S,  S,  S,  S,  S,  SL, L,  _d("low",10), M, _d("medium",10), _d("medium",10), _d("medium",15), _d("medium",15), _d("medium",15), _d("medium",15), _d("medium",15), _d("medium",15), _d("medium",15), _d("medium",15), _d("medium",15)],
    18: [S,  S,  S,  S,  S,  SL, L,  _d("low",10), M, _d("medium",10), _d("medium",15), _d("medium",15), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10), _d("high",10)],
    22: [S,  S,  S,  S,  SL, L,  _d("low",10), M, _d("medium",10), _d("medium",15), _d("high",10), _d("high",10), _d("high",15), _d("high",15), _d("high",15), _d("high",15), _d("high",15), _d("high",15), _d("high",15), _d("high",15), _d("high",15)],
    26: [S,  S,  S,  SL, L,  _d("low",10), M, _d("medium",10), _d("medium",15), _d("high",10), _d("high",15), _d("high",15), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10)],
    31: [S,  S,  S,  _d("super low",10), _d("low",10), M, _d("medium",10), _d("medium",15), _d("high",10), _d("high",15), _d("super high",10), _d("super high",10), _d("super high",15), _d("super high",15), _d("super high",15), _d("super high",15), _d("super high",15), _d("super high",15), _d("super high",15), _d("super high",15), _d("super high",15)],
    35: [S,  S,  SL, L,  M,  _d("medium",10), _d("medium",15), _d("high",10), _d("high",15), _d("super high",10), _d("super high",15), _d("super high",15), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10)],
    40: [S,  S,  SL, _d("low",10), _d("medium",10), _d("medium",15), _d("high",10), _d("high",15), _d("super high",10), _d("super high",15), _d("ultra high",10), _d("ultra high",10), _d("ultra high",15), _d("ultra high",15), _d("ultra high",15), _d("ultra high",15), _d("ultra high",15), _d("ultra high",15), _d("ultra high",15), _d("ultra high",15), _d("ultra high",15)],
}

# ── GROUP C: Friday ───────────────────────────────────────────────────────────
#            -2  -1   0   1   2   3   4   6   8  10  12  16   20  24  30  36  42  48  60  72 720
_C = {
    0:  [S,  S,  S,  S,  S,  S,  S,  SL, L,  M,  _d("medium",10), H,  _d("high",10), SH, SH, SH, SH, SH, SH, SH, SH],
    4:  [S,  S,  S,  S,  S,  S,  SL, L,  M,  _d("medium",10), H, _d("high",10), SH, _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10), _d("super high",10)],
    9:  [S,  S,  S,  S,  S,  SL, L,  M,  _d("medium",10), H,  SH, SH, _d("super high",10), UH, UH, UH, UH, UH, UH, UH, UH],
    13: [S,  S,  S,  S,  SL, L,  M,  _d("medium",10), H,  SH, _d("super high",10), _d("super high",10), UH, _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10), _d("ultra high",10)],
    18: [S,  S,  S,  SL, L,  M,  _d("medium",10), H,  SH, _d("super high",10), UH, UH, _d("ultra high",10), SpH, SpH, SpH, SpH, SpH, SpH, SpH, SpH],
    22: [S,  S,  SL, L,  M,  _d("medium",10), H,  SH, _d("super high",10), UH, _d("ultra high",10), _d("ultra high",10), SpH, _d("special high",10), _d("special high",10), _d("special high",10), _d("special high",10), _d("special high",10), _d("special high",10), _d("special high",10), _d("special high",10)],
    26: [S,  SL, L,  M,  _d("medium",10), H,  SH, _d("super high",10), UH, _d("ultra high",10), SpH, SpH, _d("special high",10), F,  F,  F,  F,  F,  F,  F,  F],
    31: [SL, L,  M,  _d("medium",10), H,  SH, _d("super high",10), UH, _d("ultra high",10), SpH, _d("special high",10), _d("special high",10), F, _d("festive",10), _d("festive",10), _d("festive",10), _d("festive",10), _d("festive",10), _d("festive",10), _d("festive",10), _d("festive",10)],
    35: [L,  M,  _d("medium",10), H,  SH, _d("super high",10), UH, _d("ultra high",10), SpH, _d("special high",10), F,  F,  _d("festive",10), _d("festive",15), _d("festive",15), _d("festive",15), _d("festive",15), _d("festive",15), _d("festive",15), _d("festive",15), _d("festive",15)],
    40: [M,  _d("medium",10), H,  SH, _d("super high",10), _d("ultra high",10), _d("ultra high",10), SpH, _d("special high",10), F,  _d("festive",10), _d("festive",10), _d("festive",15), _d("festive",20), _d("festive",20), _d("festive",20), _d("festive",20), _d("festive",20), _d("festive",20), _d("festive",20), _d("festive",20)],
}

# Day → matrix group
_DAY_GROUP = {
    0: _A,  # Monday
    1: _A,  # Tuesday
    2: _B,  # Wednesday
    3: _B,  # Thursday
    4: _C,  # Friday
    5: _B,  # Saturday
    6: _A,  # Sunday
}

DAY_GROUP_NAMES = {0: "Mon/Tue/Sun (A)", 2: "Wed/Thu/Sat (B)", 4: "Friday (C)"}


def _seat_bucket(booked: int) -> int:
    """Return the largest seat threshold ≤ booked."""
    bucket = 0
    for t in SEAT_THRESHOLDS:
        if booked >= t:
            bucket = t
    return bucket


def _hour_col_idx(hours_ahead: float) -> int:
    """Return index into HOUR_COLS for the given hours until departure.
    Uses the largest column value ≤ hours_ahead."""
    idx = 0
    for i, h in enumerate(HOUR_COLS):
        if hours_ahead >= h:
            idx = i
    return idx


def matrix_result(booked: int, day_of_week: int, hours_ahead: float) -> tuple[str, int]:
    """Return (classification, fare_delta) from official matrix.
    classification="" → static fares zone.
    fare_delta > 0   → apply on top of classification.
    day_of_week: 0=Mon ... 6=Sun
    hours_ahead: hours until departure (negative = already departed)
    """
    group = _DAY_GROUP.get(day_of_week, _A)
    bucket = _seat_bucket(booked)
    col_idx = _hour_col_idx(hours_ahead)
    row = group.get(bucket, group[0])
    if col_idx >= len(row):
        col_idx = len(row) - 1
    return row[col_idx]


def matrix_classification(booked: int, day_of_week: int = 0, hours_ahead: float = 72) -> str:
    """Backward-compatible: return just classification."""
    cls, _ = matrix_result(booked, day_of_week, hours_ahead)
    return cls


def matrix_fare_delta(booked: int, day_of_week: int = 0, hours_ahead: float = 72) -> int:
    """Return fare delta rupees from matrix."""
    _, delta = matrix_result(booked, day_of_week, hours_ahead)
    return delta


# ── REPRICING COOLDOWN — DISABLED ────────────────────────────────────────────
def can_reprice(trip_id: int) -> bool:  return True
def mark_repriced(trip_id: int):        pass
def cooldown_remaining(trip_id: int):   return 0


# ── IDEMPOTENCY CHECK ─────────────────────────────────────────────────────────
def needs_reclassification(current_cls: str, target_cls: str) -> bool:
    def _norm(s): return s.lower().replace("_", " ").replace("-", " ").strip()
    return _norm(current_cls) != _norm(target_cls)


# ── FARE CLAMP ────────────────────────────────────────────────────────────────
def clamp_fare(fare: int) -> int:
    return max(FARE_FLOOR, min(FARE_CEILING, fare))


# ── LEGACY HELPERS (kept for compatibility) ───────────────────────────────────
def surge_extra_delta(per_hour: float) -> int:
    if per_hour > 80: return 20
    if per_hour > 50: return 15
    if per_hour > 30: return 10
    return 0

def proximity_tier_boost(departure_dt) -> int:
    """Kept for compatibility — matrix already encodes proximity."""
    return 0

def upgrade_tier(cls: str, steps: int = 1) -> str:
    idx = tier_index(cls)
    if idx < 0: return cls
    return TIER_ORDER[min(idx + steps, len(TIER_ORDER) - 1)]
