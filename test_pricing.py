"""pytest test suite — pricing matrix, surge calc, fare clamp.
Run: pytest test_pricing.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# ── pricing_rules tests ────────────────────────────────────────────────────────

def test_fare_floor():
    from pricing_rules import clamp_fare
    assert clamp_fare(100) == 299
    assert clamp_fare(299) == 299
    assert clamp_fare(500) == 500

def test_fare_no_ceiling():
    from pricing_rules import clamp_fare
    assert clamp_fare(9999) == 9999
    assert clamp_fare(50000) == 50000

def test_matrix_always_returns_classification():
    """Matrix always returns non-empty classification for any seat count."""
    from pricing_rules import matrix_result
    for booked in [0, 3, 4, 10, 35]:
        cls, delta = matrix_result(booked=booked, day_of_week=0, hours_ahead=72)
        assert cls != "", f"Expected classification for {booked} seats, got empty"
        assert isinstance(delta, int), f"delta must be int, got {type(delta)}"

def test_matrix_friday_higher_than_monday():
    """Friday (day 4) should be higher or equal tier than Monday (day 0) same conditions."""
    from pricing_rules import matrix_result, TIER_ORDER
    cls_fri, _ = matrix_result(booked=20, day_of_week=4, hours_ahead=12)
    cls_mon, _ = matrix_result(booked=20, day_of_week=0, hours_ahead=12)
    idx_fri = TIER_ORDER.index(cls_fri) if cls_fri in TIER_ORDER else -1
    idx_mon = TIER_ORDER.index(cls_mon) if cls_mon in TIER_ORDER else -1
    assert idx_fri >= idx_mon, f"Friday {cls_fri} should be >= Monday {cls_mon}"

def test_matrix_departure_windows_return_valid_tier():
    """Matrix returns valid classification for all departure windows."""
    from pricing_rules import matrix_result, TIER_ORDER
    booked = 25
    dow = 2  # Wednesday
    for hours in [0.5, 2, 6, 12, 24, 48, 72, 168]:
        cls, delta = matrix_result(booked, dow, hours_ahead=hours)
        assert cls in TIER_ORDER or cls == "", f"Unknown tier '{cls}' at {hours}h ahead"

def test_matrix_more_seats_higher_tier():
    """More seats booked → same or higher tier."""
    from pricing_rules import matrix_result, TIER_ORDER
    dow = 2
    hours = 24
    cls_low,  _ = matrix_result(10, dow, hours)
    cls_high, _ = matrix_result(35, dow, hours)
    if cls_low and cls_high:
        idx_low  = TIER_ORDER.index(cls_low)  if cls_low  in TIER_ORDER else 0
        idx_high = TIER_ORDER.index(cls_high) if cls_high in TIER_ORDER else 0
        assert idx_high >= idx_low, f"35 seats {cls_high} should be >= 10 seats {cls_low}"

# ── ai_surge tests ─────────────────────────────────────────────────────────────

def test_surge_multiplier_baseline():
    from ai_surge import _surge_multiplier
    mult = _surge_multiplier(velocity=0, seats_left=20, hours_ahead=72)
    assert mult == 1.0, f"No signals → multiplier should be 1.0, got {mult}"

def test_surge_multiplier_high_velocity():
    from ai_surge import _surge_multiplier, VELOCITY_TRIGGER
    mult = _surge_multiplier(velocity=VELOCITY_TRIGGER + 20, seats_left=20, hours_ahead=72)
    assert mult > 1.0, "High velocity should raise multiplier"

def test_surge_multiplier_last_hour():
    from ai_surge import _surge_multiplier
    mult = _surge_multiplier(velocity=0, seats_left=20, hours_ahead=0.5)
    assert mult >= 1.40, f"Last hour should add +40%, got {mult}"

def test_surge_multiplier_last_5_seats():
    from ai_surge import _surge_multiplier
    mult = _surge_multiplier(velocity=0, seats_left=4, hours_ahead=72)
    assert mult >= 1.30, f"Last 5 seats should add +30%, got {mult}"

def test_surge_multiplier_combined():
    from ai_surge import _surge_multiplier
    mult = _surge_multiplier(velocity=50, seats_left=3, hours_ahead=0.5)
    assert mult > 1.6, f"Combined extreme signals should give mult > 1.6, got {mult}"

def test_should_surge_ceiling_tier():
    from ai_surge import should_surge
    assert should_surge("festive", velocity=25, seats_left=5, hours_ahead=3)
    assert should_surge("ultra high", velocity=0, seats_left=5, hours_ahead=3)
    assert should_surge("special high", velocity=25, seats_left=20, hours_ahead=10)

def test_should_surge_not_ceiling():
    from ai_surge import should_surge
    assert not should_surge("medium", velocity=50, seats_left=2, hours_ahead=0.5)
    assert not should_surge("high", velocity=50, seats_left=2, hours_ahead=0.5)

def test_should_surge_no_triggers():
    from ai_surge import should_surge
    # ceiling tier but no triggers fire
    assert not should_surge("festive", velocity=5, seats_left=20, hours_ahead=48)

def test_surge_cooldown():
    import time
    from ai_surge import _in_cooldown, _mark_surge, _surge_cooldown
    trip_id = 99999
    _surge_cooldown.pop(trip_id, None)
    assert not _in_cooldown(trip_id)
    _mark_surge(trip_id)
    assert _in_cooldown(trip_id)
    _surge_cooldown.pop(trip_id, None)  # cleanup


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
