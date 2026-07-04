"""Autonomous pricing loop.
Pricing decisions made in Python (reliable, no hallucination).
LLM only writes the plain-English summary for Slack.
"""
import os
import time
import threading
from datetime import datetime
from langchain_core.messages import HumanMessage

_paused = threading.Event()
_paused.clear()  # not paused by default

def pause():
    _paused.set()
    print("[autoloop] paused")

def resume():
    _paused.clear()
    print("[autoloop] resumed")

def is_paused() -> bool:
    return _paused.is_set()

_anomaly_last_alert: dict = {}
_ANOMALY_COOLDOWN = 1800   # 30 min per service
_MIN_HISTORY_POINTS = 5    # need enough history before firing surge alerts


# ── DATA FETCH ────────────────────────────────────────────────────────────────

def _fetch_real_data(journey_date=None) -> tuple[list[dict], dict[str, dict], str, object]:
    """Fetch live trips + velocity. Returns (svcs, velocity_map, date_label, journey_date)."""
    from api_client import get_client
    from worker import record_bookings, booking_velocity, _HISTORY
    from datetime import date

    jd = journey_date or date.today()
    date_label = jd.strftime("%A, %d %b %Y")

    import route_config as _rc
    src, dst = _rc.get_route()

    c = get_client()
    c.search_services(src, dst, journey_date=jd, refresh=True)
    svcs = c.list_services()
    record_bookings(svcs)

    velocity_map = {}
    for s in svcs:
        sn = s.get("service_number", "")
        if sn in _HISTORY and len(_HISTORY[sn]) >= _MIN_HISTORY_POINTS:
            v = booking_velocity(sn, window_min=60)
            velocity_map[sn] = v
    return svcs, velocity_map, date_label, jd


# ── PRICING DECISIONS IN PYTHON ───────────────────────────────────────────────

def _parse_dep_dt(dep_str):
    """Parse departure time string to LOCAL datetime. Returns None if unparseable.
    API returns UTC — convert to local (IST) so comparisons with datetime.now() work."""
    if not dep_str:
        return None
    try:
        from datetime import datetime as _dt, timezone as _tz
        if isinstance(dep_str, (int, float)):
            ts = int(dep_str)
            # epoch ms → seconds → local datetime
            return _dt.fromtimestamp(ts / 1000 if ts > 1e10 else ts)
        dep_str = str(dep_str)
        if "T" in dep_str or (" " in dep_str and len(dep_str) > 10):
            # Strip fractional seconds beyond 6 digits (Python <3.11 fromisoformat limit)
            import re as _re
            s = _re.sub(r'(\.\d{3})\d*', r'\g<1>000', dep_str)  # normalise to 6 frac digits
            s = s.strip()
            if s.endswith("Z"):
                # UTC timestamp — parse and convert to local
                s = s[:-1] + "+00:00"
            try:
                aware = _dt.fromisoformat(s)
                # If timezone-aware, convert to local naive
                return aware.astimezone().replace(tzinfo=None)
            except Exception:
                # Fallback: strip timezone, treat as UTC, add offset manually
                bare = _re.sub(r'[+\-]\d{2}:\d{2}$', '', s.replace("Z",""))
                utc_dt = _dt.fromisoformat(bare)
                import time as _t
                offset_sec = -_t.timezone  # local UTC offset in seconds
                from datetime import timedelta as _td
                return utc_dt + _td(seconds=offset_sec)
        return None  # time-only strings — ambiguous, don't skip
    except Exception:
        return None


def _dep_is_full_datetime(dep_str) -> bool:
    """True if dep_str contains a date component (not just a time)."""
    if not dep_str:
        return False
    s = str(dep_str)
    import re as _re
    return bool(_re.search(r"\d{4}-\d{2}-\d{2}", s) or
                (isinstance(dep_str, (int, float)) and int(dep_str) > 1e9))


def _apply_pricing(svcs: list[dict], velocity_map: dict, journey_date=None) -> list[dict]:
    """Apply matrix rules via API directly. Returns action log for summary."""
    from api_client import get_client
    from pricing_rules import (
        matrix_result, matrix_classification, needs_reclassification,
        surge_extra_delta, clamp_fare, proximity_tier_boost, upgrade_tier,
    )

    c = get_client()
    actions = []

    for s in svcs:
        sn   = s.get("service_number", "")
        tid  = s.get("trip_id")
        bkd  = int(s.get("booked") or 0)
        curr = s.get("classification") or ""
        import re as _re_short
        _m_short = _re_short.search(r"(\d{4}(?:-\d+)?(?:\s*OPT)?)\s*$", sn, _re_short.I)
        short = _m_short.group(1).strip() if _m_short else (sn.split("-")[-1] if "-" in sn else sn)
        v     = velocity_map.get(sn, {})
        vph   = v.get("per_hour", 0) if isinstance(v, dict) else 0

        if not tid:
            continue

        # Skip inactive services (portal toggle = off)
        if not s.get("is_active", True):
            print(f"[autoloop] skip {short} — inactive")
            continue

        # Parse departure datetime once — used for both skip-check and proximity boost
        dep_str = s.get("departure_time", "")
        dep_dt = _parse_dep_dt(dep_str)

        # If API returned time-only string (e.g. "22:30:00"), combine with journey date
        if dep_dt is None and dep_str:
            try:
                from datetime import datetime as _dtp, date as _dated
                _jd = journey_date or _dated.today()
                # Try HH:MM:SS or HH:MM
                for _fmt in ("%H:%M:%S", "%H:%M"):
                    try:
                        _t = _dtp.strptime(str(dep_str).strip(), _fmt)
                        dep_dt = _dtp.combine(_jd, _t.time())
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Try to use last boarding point time instead of first departure.
        # Pricing is valid until the last passenger can board — not just first stop.
        # This extends the priceable window significantly for multi-stop services.
        try:
            _last_bp = c.get_last_boarding_time(tid)
            if _last_bp and _last_bp.get("raw"):
                _last_dt = _parse_dep_dt(_last_bp["raw"])
                if _last_dt is not None:
                    dep_dt = _last_dt   # use last boarding time for hours_ahead
        except Exception:
            pass  # fallback to first departure if API fails

        # Skip ONLY if we have a full datetime (date+time) AND it's clearly in the past.
        # Time-only strings ("08:05") are ambiguous (UTC vs IST, today vs tomorrow)
        # so we never skip based on them — only skip on full ISO datetimes.
        if dep_dt is not None and _dep_is_full_datetime(dep_str):
            from datetime import datetime as _dtnow
            if dep_dt < _dtnow.now():
                print(f"[autoloop] skip {short} — last boarding passed {dep_str}")
                continue

        # Compute hours to departure for matrix lookup
        from datetime import datetime as _dtnow
        if dep_dt is not None:
            hours_ahead = (dep_dt - _dtnow.now()).total_seconds() / 3600
        else:
            hours_ahead = 72.0  # unknown → assume far out

        # Day of week from JOURNEY DATE — never from dep_dt.
        # dep_dt (last boarding) can cross midnight into next day (UTC→IST),
        # giving wrong weekday. Journey date is always correct.
        if journey_date is not None:
            day_of_week = journey_date.weekday()
        elif dep_dt is not None:
            day_of_week = dep_dt.date().weekday()
        else:
            day_of_week = _dtnow.now().weekday()

        # Saturday early-morning rule:
        # Services numbered ≤ 0700 (e.g. 0500, 0600, 0700) on Saturday
        # are Friday-night buses → apply Friday (Group C) rules.
        # Extract HHMM from service number last segment.
        if day_of_week == 5:  # Saturday
            try:
                import re as _re_svc
                # Find first 4-digit HHMM in full service number
                # e.g. BN-TP-AC-SE-0600-1 → 0600, BN-TP-AC-SE-2230 → 2230
                _svc_m = _re_svc.search(r"\b(\d{4})\b", sn)
                if _svc_m:
                    _svc_hhmm = int(_svc_m.group(1))  # e.g. 500, 600, 700, 835
                    if _svc_hhmm <= 700:
                        day_of_week = 4  # Friday (Group C)
                        print(f"[autoloop] {short}: Saturday svc≤0700 → Friday rules")
            except Exception:
                pass

        target_cls, fare_delta = matrix_result(bkd, day_of_week, hours_ahead)
        print(f"[autoloop] {short}: {bkd} seats | {hours_ahead:.1f}h ahead | day={day_of_week} -> {target_cls or 'static'} delta={fare_delta}")

        action = {
            "service": short,
            "trip_id": tid,
            "booked": bkd,
            "total_seats": int(s.get("total_seats") or 45),
            "current_cls": curr,
            "target_cls": target_cls,
            "velocity": vph,
            "done": [],
            "skipped": [],
        }

        try:
            if target_cls == "":
                # Static fares zone (matrix says so — close to departure, few seats)
                layout = c.get_seat_layout(tid)

                if not layout:
                    action["skipped"].append("no seat data available")
                else:
                    # Skip if all fares already at correct static values
                    # Invalidate cache first so we read live fares, not stale
                    c._cache_invalidate(tid)
                    fares = c.read_seat_fares(tid)
                    # Two static fare tiers based on hours to departure:
                    #   > 2h : window=399, non_window=389, last_row=349
                    #   ≤ 2h : window=349, non_window=329, last_row=299
                    if hours_ahead > 4:
                        target_map = {"window": 399, "non_window": 389, "last_row": 349}
                        fare_label = "window=399, non-window=389, last-row=349"
                    else:
                        target_map = {"window": 349, "non_window": 329, "last_row": 299}
                        fare_label = "window=349, non-window=329, last-row=299"
                    # Build flat lookup: seat_id (int or str) → current fare
                    def _get_fare(sid):
                        v = fares.get(sid) or fares.get(str(sid)) or fares.get(int(sid) if str(sid).isdigit() else sid)
                        return int(float(v)) if v is not None else None
                    # Updatable = dummy seats always, real seats only if not occupied/blocked
                    def _can_update(s):
                        if s.get("is_dummy"):
                            return True  # dummy seats always get static fare regardless of occupied flag
                        return not s.get("occupied") and not s.get("blocked")
                    updatable = [s for s in layout if _can_update(s)]
                    # already_correct: only check seats that have a known current fare
                    priced_seats = [s for s in updatable if _get_fare(s["id"]) is not None]
                    already_correct = bool(priced_seats) and all(
                        _get_fare(s["id"]) == target_map.get(s["category"], -1)
                        for s in priced_seats
                    )
                    window_ids     = [s["id"] for s in updatable if s["category"] == "window"]
                    non_window_ids = [s["id"] for s in updatable if s["category"] == "non_window"]
                    last_row_ids   = [s["id"] for s in updatable if s["category"] == "last_row"]
                    if already_correct:
                        action["skipped"].append("static fares already correct")
                    else:
                        if last_row_ids:
                            c.static_fare(tid, last_row_ids, clamp_fare(target_map["last_row"]), reason="last row seats")
                        if window_ids:
                            c.static_fare(tid, window_ids, clamp_fare(target_map["window"]), reason="window seats")
                        if non_window_ids:
                            c.static_fare(tid, non_window_ids, clamp_fare(target_map["non_window"]), reason="non - window seats")
                        action["done"].append(f"static fares: {fare_label}")

            elif target_cls:
                if not needs_reclassification(curr, target_cls):
                    action["skipped"].append(f"already {curr}")
                else:
                    # Check learning: has this action historically hurt bookings?
                    _avoid = False
                    try:
                        from state_store import learn_should_avoid
                        _avoid = learn_should_avoid(sn, "set_pricing_model",
                                                    target_cls, day_of_week)
                        if _avoid:
                            print(f"[learn] {short}: skipping {target_cls} — historically negative on day={day_of_week}")
                    except Exception:
                        pass

                    if not _avoid:
                        c.set_pricing_model(tid, classification=target_cls)
                        action["done"].append(f"{curr} -> {target_cls}")
                        # Record for learning
                        try:
                            from state_store import learn_record_action
                            _rec_id = learn_record_action(
                                sn, str(tid), "set_pricing_model",
                                classification=target_cls,
                                model_classification=target_cls,
                                manual_classification="",
                                seats_booked_before=bkd,
                                hours_to_depart=hours_ahead,
                                day_of_week=day_of_week,
                                triggered_by="autoloop",
                            )
                            if _rec_id:
                                action["learn_id"] = _rec_id
                        except Exception:
                            pass
                    else:
                        action["skipped"].append(f"learning: {target_cls} historically negative")

                # Apply matrix fare delta if > 0
                # fare_delta from matrix = rupees, but bulk_adjust uses % percentage.
                # Convert: delta_pct = round(fare_delta / avg_fare * 100)
                # Simpler: use fare_delta directly as percentage points (10 rupees ≈ 2-3%)
                # Use fare_delta as percentage directly since matrix values are 8,10,12,15,18,20,22
                if fare_delta > 0:
                    current_pct = c.get_fare_tier(tid)
                    target_pct = current_pct + fare_delta  # add delta as percentage points
                    c.bulk_adjust(adjustment_id=target_pct, trip_ids=[tid],
                                  reason="matrix fare adjustment")
                    action["done"].append(f"fare +{fare_delta}% (adj={target_pct}%)")

            # Velocity surge via bulk_adjust — +5% on surge
            if vph > 30 and tid:
                current_pct = c.get_fare_tier(tid)
                surge_pct = current_pct + 5
                c.bulk_adjust(adjustment_id=surge_pct, trip_ids=[tid],
                              reason="increase in occupancy")
                action["done"].append(f"surge +5% ({vph:.0f}/hr)")

            # AI surge — activates when matrix is at ceiling
            try:
                from ai_surge import apply_surge, CEILING_TIERS
                curr_cls = (target_cls or curr or "").lower().replace("_", " ")
                if curr_cls in CEILING_TIERS:
                    total   = int(s.get("total_seats") or 45)
                    seats_left = total - bkd
                    # Get representative current fare
                    fares = c.read_seat_fares(tid)
                    fare_vals = [int(float(v)) for v in fares.values() if v]
                    base_fare = int(sum(fare_vals) / len(fare_vals)) if fare_vals else 500
                    surge_result = apply_surge(
                        trip_id=tid,
                        service_number=sn,
                        current_fare=base_fare,
                        classification=curr_cls,
                        velocity=vph,
                        seats_left=seats_left,
                        hours_ahead=hours_ahead,
                        api_client=c,
                    )
                    if surge_result["triggered"]:
                        action["done"].append(
                            f"AI surge ₹{surge_result['old_fare']}→₹{surge_result['new_fare']}"
                            f" ({surge_result['reason']})"
                        )
                    elif surge_result["reason"] not in ("cooldown", "conditions not met"):
                        print(f"[ai_surge] {short}: {surge_result['reason']}")
            except Exception as _se:
                print(f"[ai_surge] error: {_se}")

        except Exception as e:
            action["error"] = str(e)

        actions.append(action)

    return actions


# ── SUMMARY VIA LLM ───────────────────────────────────────────────────────────

def _build_summary_prompt(actions: list[dict], date_label: str = "") -> str:
    from datetime import date
    dl = date_label or date.today().strftime("%A, %d %b %Y")
    lines = [
        f"You are writing a Slack message for the PricingCo operations team.",
        f"Journey date: {dl} | Route: Bangalore -> Tirupati",
        "Convert the following pricing actions into a clear business summary.",
        "Rules:",
        "- Only list services where something CHANGED. Do NOT list every service.",
        "- Group all unchanged services into ONE line: ⏸ No change: 0605, 0700, 2300...",
        "- For changed services: ✅ *2350 OPT*: 2/45 seats — Super High → fixed fares ₹349",
        "- End with one summary line: 📊 Overall fill: X/Y seats (Z%) across N services",
        "- Plain English. No code. No JSON. No tool names. No markdown headers.",
        "- Use emojis: ✅ changed, ⏸ no change, 📈 surge, ⚠️ watch, ❌ error",
        "",
        "ACTIONS TAKEN:",
    ]
    for a in actions:
        svc   = a["service"]
        bkd   = a["booked"]
        done  = ", ".join(a["done"])   or "none"
        skip  = ", ".join(a["skipped"]) or ""
        err   = a.get("error", "")
        vph   = a["velocity"]
        curr  = a["current_cls"]
        tgt   = a["target_cls"] or "static fares"
        line  = f"  {svc}: {bkd}/45 seats | target={tgt} | actions={done}"
        if skip:   line += f" | skipped={skip}"
        if err:    line += f" | ERROR={err}"
        if vph > 0: line += f" | velocity={vph:.1f}/hr"
        lines.append(line)

    lines.append("")
    lines.append("Write the Slack summary now (plain text, no markdown headers, no code blocks):")
    return "\n".join(lines)


# ── ANOMALY CHECK ─────────────────────────────────────────────────────────────

def _learning_evaluate():
    """Evaluate pricing actions taken 30+ min ago. Score them based on booking delta."""
    try:
        from state_store import is_available, _get_conn
        from api_client import get_client
        if not is_available():
            return
        conn = _get_conn()
        with conn.cursor() as cur:
            # Find unevaluated actions older than 30 min
            cur.execute("""
            SELECT id, service_number, trip_id, seats_booked_before
            FROM ai.pricing_learning
            WHERE evaluated_at IS NULL
              AND actioned_at < NOW() - INTERVAL '30 minutes'
            LIMIT 20
            """)
            rows = cur.fetchall()
        if not rows:
            return
        c = get_client()
        import route_config as _rc
        src, dst = _rc.get_route()
        c.search_services(src, dst, refresh=True)
        svcs = {s["service_number"]: s for s in c.list_services()}
        from state_store import learn_evaluate
        evaluated = 0
        for row in rows:
            svc_num = row["service_number"]
            svc = svcs.get(svc_num)
            if svc:
                learn_evaluate(row["id"], svc.get("booked", 0))
                evaluated += 1
        if evaluated:
            print(f"[learn] evaluated {evaluated} past pricing actions")
    except Exception as e:
        print(f"[learn] evaluation error: {e}")


def _anomaly_check():
    try:
        from worker import _HISTORY, booking_velocity
        from health import alert
        now = time.time()
        for svc in list(_HISTORY.keys()):
            # Need enough history to avoid false positives
            if len(_HISTORY.get(svc, [])) < _MIN_HISTORY_POINTS:
                continue
            if now - _anomaly_last_alert.get(svc, 0) < _ANOMALY_COOLDOWN:
                continue
            v_hr  = booking_velocity(svc, window_min=60)
            v_4hr = booking_velocity(svc, window_min=240)
            ph_hr  = v_hr.get("per_hour", 0)  if isinstance(v_hr,  dict) else 0
            ph_4hr = v_4hr.get("per_hour", 0) if isinstance(v_4hr, dict) else 0
            # Only alert if 4hr baseline is meaningful
            if ph_4hr < 2:
                continue
            if ph_hr > 3 * ph_4hr and ph_hr >= 10:
                short = svc.split("-")[-1]
                alert("warn", f"Demand surge on {short}: {ph_hr:.0f}/hr (avg {ph_4hr:.0f}/hr)")
                _anomaly_last_alert[svc] = now
            elif ph_hr < 0.3 * ph_4hr and ph_4hr >= 5:
                short = svc.split("-")[-1]
                alert("warn", f"Demand drop on {short}: {ph_hr:.0f}/hr (avg {ph_4hr:.0f}/hr)")
                _anomaly_last_alert[svc] = now
    except Exception:
        pass


def _slack_send(text: str, blocks: list = None):
    try:
        from slack_sdk import WebClient
        bot = os.environ.get("SLACK_BOT_TOKEN", "")
        ch  = os.environ.get("SLACK_CHANNEL", "")
        if bot.startswith("xoxb-") and ch:
            kwargs = {"channel": ch, "text": text}
            if blocks:
                kwargs["blocks"] = blocks
            WebClient(token=bot).chat_postMessage(**kwargs)
    except Exception:
        pass


def _route_short(src: str, dst: str) -> str:
    _abbr = {
        "BANGALORE": "BLR", "BENGALURU": "BLR",
        "TIRUPATI": "TPT",
        "HYDERABAD": "HYD",
        "VIJAYAWADA": "VJA", "VIJAYAWADA CITY": "VJA",
    }
    s = _abbr.get(src.upper(), src[:3])
    d = _abbr.get(dst.upper(), dst[:3])
    return f"{s}→{dst[:3] if d == dst[:3] else d}"


def _format_slack_blocks(actions: list[dict], ts: str, date_label: str,
                          src: str, dst: str) -> list[dict]:
    """Build Slack Block Kit payload matching the compact-table style."""
    rows_changed   = []
    rows_unchanged = []
    rows_errors    = []

    for a in actions:
        svc   = a["service"].ljust(10)
        seats = f"{a['booked']}/{a.get('total_seats', 45)}".ljust(6)
        done  = a["done"]
        err   = a.get("error")
        vph   = a["velocity"]
        curr  = a["current_cls"] or ""

        if err:
            rows_errors.append(f"  {svc} | {seats} | ❌ {err[:50]}")
        elif done:
            change = " → ".join(done)
            surge  = f"  📈 {vph:.0f}/hr" if vph > 30 else ""
            # Don't add curr prefix if done already contains the transition (e.g. "Low -> Medium")
            _has_transition = "->" in change or "→" in change
            prefix = "" if _has_transition else (f"{curr} → " if curr else "")
            rows_changed.append(f"  {svc} | {seats} | ✅ {prefix}{change}{surge}")
        else:
            display_cls = "Static" if a.get("target_cls") == "" else (curr or "No class")
            rows_unchanged.append(f"  {svc} | {seats} | ⏸ {display_cls} — no change")

    total_booked = sum(a["booked"] for a in actions)
    total_seats  = sum(a.get("total_seats", 45) for a in actions)
    fill_pct     = int(total_booked / total_seats * 100) if total_seats else 0
    route        = _route_short(src, dst)

    footer = f"  Total: {total_booked}/{total_seats} ({fill_pct}%) across {len(actions)} services"
    header = f"🕐 Pricing Review | {ts} | {route} | {date_label}"
    divider = "━" * 52
    all_rows = [header, divider] + rows_changed + rows_errors + rows_unchanged + ["", footer]
    table_text = "\n".join(all_rows)

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"```{table_text}```",
            },
        },
    ]


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def _loop(agent, interval_sec: int):
    run_count = 0
    print(f"[autoloop] ready — reviewing every {interval_sec}s")

    while True:
        if _paused.is_set():
            time.sleep(5)
            continue
        try:
            run_count += 1
            _anomaly_check()
            _learning_evaluate()

            # Step 1: fetch real data
            print("[autoloop] fetching live data...")
            svcs, velocity_map, date_label, _jd = _fetch_real_data()
            if not svcs:
                print("[autoloop] no services — skipping")
                time.sleep(interval_sec)
                continue
            print(f"[autoloop] {len(svcs)} services ({date_label}) | applying pricing rules...")

            # Step 2: AI agent makes ALL pricing decisions
            _t0 = time.time()
            actions = []  # fallback if AI fails

            if agent is not None:  # use main agent (Gemini via OpenAI endpoint)
                try:
                    from langchain_core.messages import HumanMessage
                    import route_config as _rc_ai
                    _src_ai, _dst_ai = _rc_ai.get_route()
                    _svc_lines = []
                    for s in svcs:
                        if not s.get("is_active", True):
                            continue
                        short = s.get("service_number","").split("-")[-1]
                        bkd   = s.get("booked", 0)
                        tot   = int(s.get("total_seats") or 45)
                        cls   = s.get("classification") or "Not set"
                        dep   = s.get("departure_time","")[:16]
                        # Include last boarding time for pricing window context
                        try:
                            _lbp = c.get_last_boarding_time(s.get("trip_id"))
                            _lbt = _lbp.get("time_ist","?") if _lbp else "?"
                            _lb_raw = _lbp.get("raw","") if _lbp else ""
                            from autoloop import _parse_dep_dt as _pdt
                            _lb_dt = _pdt(_lb_raw) if _lb_raw else None
                            from datetime import datetime as _dtnow_al
                            _hrs_left = round((_lb_dt - _dtnow_al.now()).total_seconds()/3600, 1) if _lb_dt else None
                            _lb_info = f" | last_boarding={_lbt} ({_hrs_left}h left)" if _hrs_left is not None else ""
                        except Exception:
                            _lb_info = ""
                        _svc_lines.append(f"  {short}: {bkd}/{tot} booked | cls={cls} | dep={dep}{_lb_info}")

                    from datetime import date as _d_now, timedelta as _td_now
                    _today_str = _d_now.today().strftime("%A, %d %b %Y")
                    _tomorrow_str = (_d_now.today() + _td_now(days=1)).strftime("%A, %d %b %Y")
                    _ai_prompt = (
                        f"TODAY IS {_today_str}. TOMORROW IS {_tomorrow_str}.\n"
                        f"AUTOLOOP RUN — pricing {date_label} | {_src_ai} → {_dst_ai}\n\n"
                        f"Service snapshot:\n" + "\n".join(_svc_lines) + "\n\n"
                        f"EXECUTE in order — no text, only tool calls:\n"
                        f"1. search_services + list_services — get live data from Postgres (trips, bookings, classification)\n"
                        f"2. set_pricing_model / static_fare / bulk_adjust — apply ALL classification, static fare, and bus fare adjustment changes in one batch via Admin API\n"
                        f"3. One-line summary: only if changes were made, else reply NO_CHANGES\n\n"
                        f"SKIP RULES (do NOT call any write tool if already correct):\n"
                        f"- Service already has static fare (has_static_fare=true) → skip, do NOT set static again\n"
                        f"- Service classification already matches target → skip set_pricing_model\n"
                        f"- Fare adjustment already at correct tier → skip bulk_adjust\n"
                        f"NOTE: call_mcp_tool(pricing_alerts) only on anomaly (zero bookings close to departure, velocity >30/hr)"
                    )
                    # Fresh thread per run — no history bleed between runs
                    import uuid as _uuid
                    _ai_thread = f"autoloop-{_uuid.uuid4().hex[:8]}"
                    _ai_result = agent.invoke(
                        {"messages": [HumanMessage(content=_ai_prompt)]},
                        config={"configurable": {"thread_id": _ai_thread}, "recursion_limit": 40},
                    )
                    _ai_msgs = _ai_result.get("messages") or []
                    print(f"[autoloop-ai] {len(_ai_msgs)} messages from AI")

                    # Hallucination check: if no ToolMessage in history → LLM wrote text instead of calling tools
                    _tool_msgs = [m for m in _ai_msgs if type(m).__name__ == "ToolMessage"]
                    if not _tool_msgs:
                        print(f"[autoloop-ai] HALLUCINATION detected — no tool calls executed. Retrying...")
                        _retry_prompt = (
                            "STOP writing text descriptions of tool calls. "
                            "You MUST call the actual tools directly using the tool_call mechanism. "
                            "Do NOT write 'Calling search_services...' — EXECUTE it. "
                            "Call search_services NOW, then list_services, then apply pricing changes."
                        )
                        _ai_result = agent.invoke(
                            {"messages": [HumanMessage(content=_retry_prompt)]},
                            config={"configurable": {"thread_id": _ai_thread}, "recursion_limit": 40},
                        )
                        _ai_msgs = _ai_result.get("messages") or []
                        _tool_msgs = [m for m in _ai_msgs if type(m).__name__ == "ToolMessage"]
                        print(f"[autoloop-ai] retry: {len(_tool_msgs)} tool calls executed")

                    # Build actions from AI tool calls — format as clean block table
                    _ai_actions = {}  # svc_num → {done, booked, total_seats}
                    for _mm in _ai_msgs:
                        # Collect tool calls (what AI decided to do)
                        for _tc in getattr(_mm, "tool_calls", []) or []:
                            _tn = _tc.get("name","")
                            _ta = _tc.get("args", {})
                            if _tn == "set_pricing_model":
                                _tid = str(_ta.get("trip_id",""))
                                _cls = _ta.get("classification","")
                                # Find service for this trip_id
                                _svc = next((s for s in svcs if str(s.get("trip_id")) == _tid), None)
                                if _svc:
                                    _sn = _svc["service_number"].split("-")[-1]
                                    if _sn not in _ai_actions:
                                        _ai_actions[_sn] = {"done":[], "skipped":[], "booked": _svc.get("booked",0),
                                                             "total_seats": int(_svc.get("total_seats") or 45),
                                                             "current_cls": _svc.get("classification",""),
                                                             "target_cls": _cls, "velocity": 0, "service": _sn,
                                                             "trip_id": int(_tid)}
                                    _prev = _svc.get("classification","")
                                    _ai_actions[_sn]["done"].append(f"{_prev} -> {_cls}" if _prev else _cls)
                            elif _tn == "static_fare":
                                _tid = str(_ta.get("trip_id",""))
                                _svc = next((s for s in svcs if str(s.get("trip_id")) == _tid), None)
                                if _svc:
                                    _sn = _svc["service_number"].split("-")[-1]
                                    if _sn not in _ai_actions:
                                        _ai_actions[_sn] = {"done":[], "skipped":[], "booked": _svc.get("booked",0),
                                                             "total_seats": int(_svc.get("total_seats") or 45),
                                                             "current_cls": _svc.get("classification",""),
                                                             "target_cls": "", "velocity": 0, "service": _sn,
                                                             "trip_id": int(_tid)}
                                    _fare = _ta.get("fare","")
                                    _ai_actions[_sn]["done"].append(f"static fare Rs.{_fare}")

                    # Add unchanged services
                    for _svc in svcs:
                        if not _svc.get("is_active", True): continue
                        _sn = _svc["service_number"].split("-")[-1]
                        if _sn not in _ai_actions:
                            _ai_actions[_sn] = {"done":[], "skipped":["no change needed"],
                                                 "booked": _svc.get("booked",0),
                                                 "total_seats": int(_svc.get("total_seats") or 45),
                                                 "current_cls": _svc.get("classification",""),
                                                 "target_cls": _svc.get("classification",""),
                                                 "velocity": 0, "service": _sn,
                                                 "trip_id": _svc.get("trip_id")}

                    # Check if agent made any actual changes
                    _has_changes = any(a["done"] for a in _ai_actions.values())

                    # Check if final message is NO_CHANGES
                    _last_msg = ""
                    for _mm in reversed(_ai_msgs):
                        if hasattr(_mm, "content") and isinstance(_mm.content, str) and _mm.content.strip():
                            _last_msg = _mm.content.strip()
                            break
                    _no_changes = "NO_CHANGES" in _last_msg.upper() or not _has_changes

                    if _has_changes and not _no_changes:
                        _ai_action_list = list(_ai_actions.values())
                        ts_ai = datetime.now().strftime("%I:%M %p")
                        import route_config as _rc3
                        _s3, _d3 = _rc3.get_route()
                        _blocks = _format_slack_blocks(_ai_action_list, ts_ai, date_label, _s3, _d3)
                        # Replace header to show AI tag
                        if _blocks:
                            _blocks[0]["text"]["text"] = _blocks[0]["text"]["text"].replace(
                                "Pricing Review", "🤖 AI Pricing Review")
                        _slack_send(f"AI Pricing Review — {ts_ai} | {date_label}", blocks=_blocks)
                        print(f"[autoloop-ai] sent block with {len(_ai_action_list)} services")
                    else:
                        print(f"[autoloop-ai] no changes — Slack skipped")
                except Exception as _ae:
                    print(f"[autoloop-ai] error: {_ae}")
                    # Matrix only as emergency fallback — agent unavailable
            else:
                # No agent — emergency matrix fallback
                print(f"[autoloop] no AI agent — using matrix fallback")
                actions = _apply_pricing(svcs, velocity_map, journey_date=_jd)

            _duration = round(time.time() - _t0, 2)

            # Step 3: send Python matrix Slack only if AI wasn't used (fallback case)
            if actions:  # only if fell back to Python matrix
                ts = datetime.now().strftime("%I:%M %p")
                import route_config as _rc2
                _src, _dst = _rc2.get_route()
                blocks = _format_slack_blocks(actions, ts, date_label, _src, _dst)
                fallback = _plain_summary(actions)
                if fallback:
                    print(f"[autoloop] {fallback[:300]}")
                _slack_send(f"Pricing Review — {ts} | {date_label}", blocks=blocks)

            # Step 4: log run to autoloop_runs table
            try:
                from state_store import record_autoloop_run
                from datetime import date as _date
                _changed  = sum(1 for a in actions if a["done"])
                _skipped  = sum(1 for a in actions if a["skipped"] and not a["done"])
                _errored  = sum(1 for a in actions if a.get("error"))
                _bkd_tot  = sum(a["booked"] for a in actions)
                _seat_tot = sum(a.get("total_seats", 45) for a in actions)
                _fill     = round(_bkd_tot / _seat_tot * 100, 1) if _seat_tot else 0
                record_autoloop_run(
                    journey_date=_date.today(),
                    route=f"{_src} -> {_dst}",
                    services_checked=len(actions),
                    services_changed=_changed,
                    services_skipped=_skipped,
                    services_errored=_errored,
                    total_seats_booked=_bkd_tot,
                    total_seats=_seat_tot,
                    fill_pct=_fill,
                    duration_seconds=_duration,
                )
            except Exception as _re:
                print(f"[autoloop] run log error: {_re}")

        except Exception as e:
            err = str(e).lower()
            if any(w in err for w in ("rate", "429", "quota", "limit")):
                print("[autoloop] rate limited — skipping this run")
            else:
                import traceback as _tb
                tb = _tb.format_exc()[-800:]
                print(f"[autoloop] error: {e}\n{tb}")
                try:
                    ts = datetime.now().strftime("%H:%M:%S")
                    _slack_send(f"🚨 *Autoloop crash at {ts}*\n```{str(e)[:300]}```\nCheck server logs.")
                except Exception:
                    pass

        time.sleep(interval_sec)


def _plain_summary(actions: list[dict]) -> str:
    """Fallback summary — only show changed services, skip noise."""
    changed = []
    unchanged = []
    errors = []

    for a in actions:
        svc  = a["service"]
        bkd  = a["booked"]
        done = a["done"]
        err  = a.get("error")
        vph  = a["velocity"]
        curr = a["current_cls"]
        tgt  = a["target_cls"] or "static fares"

        if err:
            errors.append(f"❌ *{svc}*: {err}")
        elif done:
            change = " → ".join(done)
            surge  = f" 📈 surge {vph:.0f}/hr" if vph > 30 else ""
            changed.append(f"✅ *{svc}*: {bkd}/45 seats booked — {change}{surge}")
        else:
            unchanged.append(svc)

    lines = []
    lines += changed
    lines += errors

    if unchanged:
        # Summarise no-change services in one line — not 8 separate lines
        lines.append(f"⏸ No change needed: {', '.join(unchanged)}")

    total_booked = sum(a["booked"] for a in actions)
    total_seats  = sum(a.get("total_seats", 45) for a in actions)
    fill_pct     = int(total_booked / total_seats * 100) if total_seats else 0
    lines.append(f"\n📊 Overall fill: *{total_booked}/{total_seats}* seats ({fill_pct}%) across {len(actions)} services")

    return "\n".join(lines)


def start(agent):
    interval = int(os.environ.get("AUTOLOOP_SEC", "0"))
    if interval <= 0:
        print("[autoloop] disabled (set AUTOLOOP_SEC > 0 to enable)")
        return
    t = threading.Thread(target=_loop, args=(agent, interval), daemon=True, name="autoloop")
    t.start()
    print(f"[autoloop] started — interval={interval}s")
