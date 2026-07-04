"""AI Surge Engine — activates when matrix is at ceiling.

Analyzes demand signals and auto-applies fare above matrix max.
No approval needed. Posts Slack notification after every action.

Conditions checked:
  1. Matrix classification = ceiling tier (festive/special high/ultra high)
  2. Velocity > threshold OR seats remaining < threshold OR hours < threshold
  3. Not in surge cooldown (30 min per trip)

Surge calculation:
  base_surge = current_fare
  multiplier  = driven by velocity + scarcity + proximity
  new_fare    = base_surge * multiplier  (no upper cap)
"""

import time
import os
from datetime import datetime

# ── CEILING TIERS — AI surge activates when matrix hits these ────────────────
CEILING_TIERS = {"festive", "special high", "ultra high"}

# ── SURGE COOLDOWN ────────────────────────────────────────────────────────────
_surge_cooldown: dict[int, float] = {}   # trip_id → last surge timestamp
SURGE_COOLDOWN_SEC = 1800                # 30 min between AI surges per trip

# ── SURGE THRESHOLDS ─────────────────────────────────────────────────────────
VELOCITY_TRIGGER   = 20   # bookings/hr — surge if above this
SEATS_LEFT_TRIGGER = 10   # seats remaining — surge if below this
HOURS_LEFT_TRIGGER = 6    # hours to departure — surge if below this


def _in_cooldown(trip_id: int) -> bool:
    last = _surge_cooldown.get(trip_id, 0)
    return (time.time() - last) < SURGE_COOLDOWN_SEC


def _mark_surge(trip_id: int):
    _surge_cooldown[trip_id] = time.time()


def _surge_multiplier(velocity: float, seats_left: int, hours_ahead: float) -> float:
    """Calculate fare multiplier based on demand signals.
    Returns 1.0 (no change) to ~2.5 (extreme demand).
    """
    mult = 1.0

    # Velocity component: +5% per 10 bookings/hr above trigger
    if velocity > VELOCITY_TRIGGER:
        excess = velocity - VELOCITY_TRIGGER
        mult += (excess / 10) * 0.05

    # Scarcity component: fewer seats = higher multiplier
    if seats_left <= 5:
        mult += 0.30   # last 5 seats → +30%
    elif seats_left <= 10:
        mult += 0.20   # last 10 seats → +20%
    elif seats_left <= 15:
        mult += 0.10   # last 15 seats → +10%

    # Proximity component: closer to departure = higher price
    if hours_ahead <= 1:
        mult += 0.40   # last hour → +40%
    elif hours_ahead <= 3:
        mult += 0.25   # last 3h → +25%
    elif hours_ahead <= 6:
        mult += 0.15   # last 6h → +15%
    elif hours_ahead <= 12:
        mult += 0.08   # last 12h → +8%

    return round(mult, 2)


def should_surge(classification: str, velocity: float,
                 seats_left: int, hours_ahead: float) -> bool:
    """Return True if AI surge conditions are met."""
    if classification.lower().replace("_", " ") not in CEILING_TIERS:
        return False  # matrix not at ceiling yet
    triggers = [
        velocity > VELOCITY_TRIGGER,
        seats_left < SEATS_LEFT_TRIGGER,
        hours_ahead < HOURS_LEFT_TRIGGER,
    ]
    return any(triggers)  # at least one trigger must fire


def apply_surge(trip_id: int, service_number: str, current_fare: int,
                classification: str, velocity: float,
                seats_left: int, hours_ahead: float,
                api_client) -> dict:
    """Apply AI surge fare to all seats. Returns action dict."""
    result = {
        "triggered": False,
        "reason": "",
        "old_fare": current_fare,
        "new_fare": current_fare,
        "multiplier": 1.0,
    }

    if _in_cooldown(trip_id):
        result["reason"] = "cooldown"
        return result

    if not should_surge(classification, velocity, seats_left, hours_ahead):
        result["reason"] = "conditions not met"
        return result

    mult = _surge_multiplier(velocity, seats_left, hours_ahead)
    if mult <= 1.0:
        result["reason"] = "multiplier <= 1.0, no change"
        return result

    new_fare = int(current_fare * mult)
    from pricing_rules import clamp_fare
    new_fare = clamp_fare(new_fare)  # only enforces floor ₹299

    # Apply to all seats via seat layout
    try:
        layout = api_client.get_seat_layout(trip_id)
        if not layout:
            result["reason"] = "no seat layout"
            return result

        all_seat_ids = [s["id"] for s in layout]

        # Read fares BEFORE change — for undo + min/max reporting
        api_client._cache_invalidate(trip_id)
        pre_fares = api_client.read_seat_fares(trip_id)
        pre_vals  = [int(float(v)) for v in pre_fares.values() if v]
        old_min   = min(pre_vals) if pre_vals else current_fare
        old_max   = max(pre_vals) if pre_vals else current_fare

        # Save undo record BEFORE applying — so ops can reply "undo" in Slack
        try:
            import slack_listener as _sl
            prev_fares_by_seat = {str(s["id"]): pre_fares.get(s["name"]) or pre_fares.get(str(s["id"]))
                                  for s in layout}
            with _sl._last_action_lock:
                _sl._last_action[str(trip_id)] = {
                    "action": "static_fare",
                    "prev_state": {"prev_fares": prev_fares_by_seat},
                    "service_number": service_number,
                }
            from state_store import undo_save
            undo_save(str(trip_id), "static_fare",
                      {"prev_fares": prev_fares_by_seat}, service_number)
        except Exception:
            pass

        api_client.static_fare(trip_id, all_seat_ids, new_fare,
                               reason="AI surge — peak demand")

        # Build reason string
        reasons = []
        if velocity > VELOCITY_TRIGGER:
            reasons.append(f"velocity {velocity:.0f}/hr")
        if seats_left < SEATS_LEFT_TRIGGER:
            reasons.append(f"{seats_left} seats left")
        if hours_ahead < HOURS_LEFT_TRIGGER:
            reasons.append(f"{hours_ahead:.1f}h to dep")

        _mark_surge(trip_id)

        # Read fares AFTER change for min/max
        api_client._cache_invalidate(trip_id)
        post_fares = api_client.read_seat_fares(trip_id)
        post_vals  = [int(float(v)) for v in post_fares.values() if v]
        new_min    = min(post_vals) if post_vals else new_fare
        new_max    = max(post_vals) if post_vals else new_fare

        result.update({
            "triggered": True,
            "reason":    " + ".join(reasons),
            "new_fare":  new_fare,
            "multiplier": mult,
            "old_min": old_min, "old_max": old_max,
            "new_min": new_min, "new_max": new_max,
        })

        # Log to surge_log table
        try:
            from state_store import record_surge
            record_surge(
                trip_id=str(trip_id), service_number=service_number,
                trigger_reason=result["reason"], multiplier=mult,
                fare_min_before=old_min, fare_max_before=old_max,
                fare_min_after=new_min, fare_max_after=new_max,
                seats_left=seats_left, velocity_per_hr=velocity,
                hours_to_depart=hours_ahead,
            )
        except Exception:
            pass

        # Slack notification
        sn = service_number.split("-")[-1] if "-" in service_number else service_number
        _notify(sn, classification, mult, result["reason"],
                old_min, old_max, new_min, new_max)

    except Exception as e:
        result["reason"] = f"error: {e}"

    return result


def _notify(service: str, cls: str, mult: float, reason: str,
            old_min: int, old_max: int, new_min: int, new_max: int):
    try:
        from slack_sdk import WebClient
        bot = os.environ.get("SLACK_BOT_TOKEN", "")
        ch  = os.environ.get("SLACK_CHANNEL", "")
        if not (bot.startswith("xoxb-") and ch):
            return
        ts  = datetime.now().strftime("%I:%M %p")
        pct = int((mult - 1) * 100)
        msg = (
            f"🚀 *AI Surge — {service}* | {ts}\n"
            f"Trigger: {reason} | Matrix ceiling: *{cls}* | Multiplier: {mult}x (+{pct}%)\n"
            f"```"
            f"         Min      Max\n"
            f"Before  ₹{old_min:<7} ₹{old_max}\n"
            f"After   ₹{new_min:<7} ₹{new_max}"
            f"```\n"
            f"Reply *undo* to reverse."
        )
        WebClient(token=bot).chat_postMessage(channel=ch, text=msg)
    except Exception:
        pass
