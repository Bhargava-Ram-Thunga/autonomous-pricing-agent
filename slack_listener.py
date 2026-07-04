"""Slack Socket Mode listener â€” hybrid: fast lane for reads, AI for decisions."""
import os
import time
import threading
from langchain_core.messages import HumanMessage

_agent_ref = {"agent": None}
_started = False
_lock = threading.Lock()


def _detect_service(text: str) -> str | None:
    import re as _r
    # Full service number any route (BN-TP-..., HYD-VJY-..., etc.)
    m = _r.search(r"\b([A-Z]{2,3}-[A-Z]{2,3}-[A-Z]{2}-[A-Z]{2}-\d{3,4}[A-Z]{0,3}(?:\s*OPT)?)\b", text, _r.I)
    if m:
        return m.group(1).strip().upper()
    # Bare number â€” prefix with current route
    m = _r.search(r"\b(\d{3,4}[A-Z]{0,3})\s*(opt)?\b", text, _r.I)
    if m:
        try:
            import route_config as _rc
            src, dst = _rc.get_route()
            _abbr = {"BANGALORE": "BN", "BENGALURU": "BN", "HYDERABAD": "HYD",
                     "TIRUPATI": "TP", "VIJAYAWADA": "VJY"}
            s = _abbr.get(src.upper(), src[:2].upper())
            d = _abbr.get(dst.upper(), dst[:2].upper())
            suffix = " OPT" if m.group(2) else ""
            return f"{s}-{d}-AC-SE-{m.group(1).upper()}{suffix}"
        except Exception:
            return f"BN-TP-AC-SE-{m.group(1)}{' OPT' if m.group(2) else ''}"
    return None


def _svc_label(x: dict) -> str:
    sn = x.get("service_number", "")
    booked = x.get("booked", 0)
    total = int(x.get("total_seats") or 45)
    rng = x.get("range", "")
    cls = x.get("classification") or "Not set"
    # BN-TP-AC-SE-0600-1 â†’ "0600-1", BN-TP-AC-SE-2230 â†’ "2230"
    import re as _re_sl
    _m_sl = _re_sl.search(r"(\d{4}(?:-\d+)?(?:\s*OPT)?)\s*$", sn, _re_sl.I)
    short = _m_sl.group(1).strip().replace(" OPT", " (OPT)") if _m_sl else (sn.split("-")[-1] if "-" in sn else sn)
    fill_pct = f"{int(booked)/total*100:.0f}%" if total else "0%"
    fare_part = f" | â‚¹{rng}" if rng else ""
    # Departure time â€” extract HH:MM from ISO string
    dep_str = x.get("departure_time", "")
    dep_part = ""
    if dep_str:
        try:
            import re as _r
            m = _r.search(r'T(\d{2}:\d{2})', dep_str)
            dep_part = f" | ðŸ• {m.group(1)}" if m else ""
        except Exception:
            pass
    return f"ðŸšŒ *{short}*: {booked}/{total} seats ({fill_pct}) | {cls}{fare_part}{dep_part}"


_last_date: dict = {}    # user_id -> last date context from their messages
_last_action: dict = {}  # trip_id -> {action, prev_state} for undo
_last_action_lock = threading.Lock()


def _load_undo_from_db():
    """Restore undo store from Postgres on startup."""
    global _last_action
    try:
        from state_store import undo_load_all
        loaded = undo_load_all()
        with _last_action_lock:
            _last_action.update(loaded)
        if loaded:
            print(f"[slack] restored {len(loaded)} undo records from Postgres")
    except Exception as e:
        print(f"[slack] undo restore failed: {e}")


def _build_handle(agent):
    def handle(text: str, _say_fn, user_id: str = "default", thread_ts: str | None = None):
        def say(msg=None, blocks=None):
            try:
                kwargs = {}
                if msg:
                    kwargs["text"] = msg
                if blocks:
                    kwargs["blocks"] = blocks
                    if not msg:
                        kwargs["text"] = "Pricing update"  # Slack requires text as fallback
                if thread_ts:
                    kwargs["thread_ts"] = thread_ts
                _say_fn(**kwargs)
            except Exception as _se:
                print(f"[slack] say error: {_se}")

        text = (text or "").strip()
        if not text:
            return

        import re as _re
        from datetime import date as _d, timedelta as _td
        s = text.lower()
        today = _d.today()
        target_date = None    # set below if message mentions a specific date
        target_dates = []     # set below for multi-date commands e.g. "04 and 05 june"

        # â”€â”€ USER ROUTE RESOLUTION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Each user can have their own assigned route.
        # All route lookups in this handler use _user_src/_user_dst.
        def _get_user_route():
            try:
                from state_store import user_route_get
                r = user_route_get(user_id)
                if r:
                    return r
            except Exception:
                pass
            try:
                import route_config as _rc
                return _rc.get_route()
            except Exception:
                return ("BANGALORE", "TIRUPATI")

        # â”€â”€ USER ROUTE COMMANDS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # "assign route bangalore tirupati to @U123" or "set my route to blr tpt"
        _assign_m = _re.search(
            r"\b(assign|set|give|add)\b.*(route|path)\b.*\b(\w+)\b.*\b(to|->|â†’)\b.*\b(\w+)\b.*<@(\w+)>", s
        ) or _re.search(
            r"<@(\w+)>.*\b(route|path)\b.*\b(\w+)\b.*\b(to|->|â†’)\b.*\b(\w+)\b", s
        )
        # "my route is bangalore tirupati" or "set my route bangalore tirupati"
        _my_route_m = _re.search(
            r"\b(my route|set my route|change my route|my route is)\b.*\b(\w[\w\s]+)\b.*\b(to|->|â†’)\b.*\b(\w+)\b", s
        )
        # "show all users" / "list users" / "who has access" / "show user routes"
        if _re.search(r"\b(show|list|who)\b.*(user|people|person|member|team|access|route assign)\b", s) \
                or _re.search(r"\b(user|people).*(route|assign|access)\b", s) \
                or s.strip() in ("list users", "show users", "users", "team routes",
                                 "show user routes", "user routes", "who has access",
                                 "show team", "team", "members"):
            try:
                from state_store import user_route_list
                rows = user_route_list()
                if not rows:
                    say("No users assigned yet. Use: `assign route <src> to <dst> to @user`")
                else:
                    lines = ["*ðŸ‘¥ User Route Assignments:*"]
                    for r in rows:
                        name = r.get("display_name") or r.get("slack_user_id")
                        src  = r.get("source", "")
                        dst  = r.get("destination", "")
                        by   = r.get("assigned_by", "")
                        lines.append(f"  <@{r['slack_user_id']}> ({name}) â†’ *{src}* â†’ *{dst}*  _(by {by})_")
                    say("\n".join(lines))
            except Exception as e:
                say(f"âŒ Error: {e}")
            return

        # "remove route for @user" / "unassign @user"
        _remove_m = _re.search(r"\b(remove|delete|unassign|clear)\b.*(route|access).*<@(\w+)>", s) \
                    or _re.search(r"<@(\w+)>.*\b(remove|delete|unassign|clear)\b.*(route|access)", s)
        if _remove_m:
            try:
                target_uid = _remove_m.group(3) if _remove_m.lastindex >= 3 else _remove_m.group(1)
                from state_store import user_route_delete
                user_route_delete(target_uid)
                say(f"âœ… Route removed for <@{target_uid}> â€” falls back to global default.")
            except Exception as e:
                say(f"âŒ Error: {e}")
            return

        # "assign route bangalore tirupati to @U123" / "assign blr tpt to @user"
        # Strategy: extract @mention, then find two station names in remaining text
        _assign_full = _re.search(r"<@(\w+)>", text)
        _has_assign  = _re.search(r"\b(assign|set|give|add)\b", s)
        if _assign_full and _has_assign:
            try:
                target_uid = _assign_full.group(1)
                # Strip the mention and action words, find station names
                _clean = _re.sub(r"<@\w+>", "", s)
                _clean = _re.sub(r"\b(assign|set|give|add|route|path|to|for|the|a|an|is|my|your|their|our)\b", " ", _clean)
                _clean = _re.sub(r"\s+", " ", _clean).strip()
                _tokens = [t for t in _clean.split() if len(t) >= 3]
                if len(_tokens) < 2:
                    say("âŒ Need two station names. Example: `assign route bangalore tirupati to @user`")
                    return
                # Resolve station abbreviations
                _ABBR = {
                    "blr": "BANGALORE", "bng": "BANGALORE", "bangalore": "BANGALORE", "bengaluru": "BANGALORE",
                    "tpt": "TIRUPATI",  "trp": "TIRUPATI",  "tirupati": "TIRUPATI",
                    "hyd": "HYDERABAD", "hyderabad": "HYDERABAD",
                    "vjy": "VIJAYAWADA","vja": "VIJAYAWADA","vijayawada": "VIJAYAWADA",
                    "chn": "CHENNAI",   "chennai": "CHENNAI",
                    "mys": "MYSORE",    "mysore": "MYSORE",
                    "vsk": "VISAKHAPATNAM", "vizag": "VISAKHAPATNAM", "visakhapatnam": "VISAKHAPATNAM",
                }
                src = _ABBR.get(_tokens[0].lower(), _tokens[0].upper())
                dst = _ABBR.get(_tokens[1].lower(), _tokens[1].upper())
                # Try to get display name from Slack
                display_name = target_uid
                try:
                    from slack_sdk import WebClient as _WC
                    _wc = _WC(token=os.environ.get("SLACK_BOT_TOKEN", ""))
                    _info = _wc.users_info(user=target_uid)
                    display_name = (_info["user"].get("real_name")
                                    or _info["user"].get("name")
                                    or target_uid)
                except Exception:
                    pass
                from state_store import user_route_set
                user_route_set(target_uid, src, dst,
                               display_name=display_name, assigned_by=user_id)
                say(f"âœ… <@{target_uid}> assigned route: *{src}* â†’ *{dst}*")
            except Exception as e:
                say(f"âŒ Error: {e}")
            return

        # "set my route to bangalore tirupati"
        _my_route_trigger = _re.search(r"\b(my route|set my route|change my route)\b", s)
        if _my_route_trigger:
            try:
                _ABBR = {
                    "blr": "BANGALORE", "bng": "BANGALORE", "bangalore": "BANGALORE", "bengaluru": "BANGALORE",
                    "tpt": "TIRUPATI",  "tirupati": "TIRUPATI",
                    "hyd": "HYDERABAD", "hyderabad": "HYDERABAD",
                    "vjy": "VIJAYAWADA","vja": "VIJAYAWADA","vijayawada": "VIJAYAWADA",
                    "chn": "CHENNAI",   "chennai": "CHENNAI",
                    "mys": "MYSORE",    "mysore": "MYSORE",
                }
                # Strip noise words, find two station tokens
                _mc = _re.sub(r"\b(my|route|set|change|is|to|for|the|a|an)\b", " ", s)
                _mc = _re.sub(r"\s+", " ", _mc).strip()
                _mt = [t for t in _mc.split() if len(t) >= 3 and not t.isdigit()]
                if len(_mt) < 2:
                    say("âŒ Need two stations. Example: `my route is bangalore tirupati`")
                    return
                src = _ABBR.get(_mt[0], _mt[0].upper())
                dst = _ABBR.get(_mt[1], _mt[1].upper())
                display_name = user_id
                try:
                    from slack_sdk import WebClient as _WC
                    _wc = _WC(token=os.environ.get("SLACK_BOT_TOKEN", ""))
                    _info = _wc.users_info(user=user_id)
                    display_name = (_info["user"].get("real_name")
                                    or _info["user"].get("name") or user_id)
                except Exception:
                    pass
                from state_store import user_route_set
                user_route_set(user_id, src, dst,
                               display_name=display_name, assigned_by=user_id)
                say(f"âœ… Your route set to: *{src}* â†’ *{dst}*")
            except Exception as e:
                say(f"âŒ Error: {e}")
            return

        # "my route" / "what is my route" / "show my route"
        if _re.search(r"\b(my route|what.*(my|current).*(route|path)|show.*my.*route)\b", s) \
                or s.strip() in ("my route", "what is my route", "show my route",
                                 "which route am i on", "my current route"):
            try:
                r = _get_user_route()
                from state_store import user_route_get
                assigned = user_route_get(user_id)
                if assigned:
                    say(f"ðŸ“ Your assigned route: *{r[0]}* â†’ *{r[1]}*")
                else:
                    say(f"ðŸ“ No personal route set. Using global default: *{r[0]}* â†’ *{r[1]}*\nSet yours: `my route is bangalore tirupati`")
            except Exception as e:
                say(f"âŒ Error: {e}")
            return

        # â”€â”€ FAST LANE: read-only / status queries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # These never need AI â€” direct portal scrape, instant response

        # Help command
        if s.strip() in (
                # Basic
                "help", "/help", "commands", "command list",
                "what can you do", "what can i ask", "what can we ask",
                "show commands", "show help", "show all commands",
                "how to use", "usage", "what do you support",
                "capabilities", "features", "what are your features",
                "what are your capabilities", "what do you know",
                "what can you handle", "what can you answer",
                "tell me what you can do", "tell me your commands",
                "list commands", "list all commands", "all commands",
                "how does this work", "how do i use this",
                "how do i use you", "how can i use you",
                "how can i talk to you", "how should i talk to you",
                "how do i talk to you", "how do i interact with you",
                "what questions can i ask", "what questions can you answer",
                "i don't know what to ask", "what should i ask",
                "getting started", "guide", "user guide",
                "cheat sheet", "quick reference", "reference",
                "supported commands", "supported queries",
                "what commands do you support", "what queries do you support",
                "menu", "options", "show options", "show menu",
                "what are my options", "what are the options",
                "huh", "?", "??", "???",
                # Natural human phrasing
                "yo what can you do",
                "hey what can you do",
                "bro what can you do",
                "what do you do",
                "what exactly do you do",
                "what all can you do",
                "what all do you do",
                "so what can you do",
                "ok what can you do",
                "alright what can you do",
                "tell me what you can do",
                "tell me what all you can do",
                "tell me everything you can do",
                "show me what you can do",
                "show me what you got",
                "what you got",
                "what do you know",
                "what all do you know",
                "what topics do you cover",
                "what do you handle",
                "what tasks can you do",
                "what tasks do you handle",
                "what kind of questions can i ask",
                "what kind of things can i ask",
                "what kind of things can you do",
                "what sort of questions can i ask",
                "what sort of things can you do",
                "what type of questions can i ask",
                "what type of things can you help with",
                "what can i type here",
                "what should i type",
                "what do i type",
                "what do i say",
                "what can i say",
                "what can i say to you",
                "what should i say",
                "i have no idea what to ask",
                "i dont know what to ask",
                "i don't know what to ask",
                "i dont know how to use this",
                "i don't know how to use this",
                "not sure what to ask",
                "not sure how to use this",
                "how do i start",
                "where do i start",
                "where to start",
                "how to start",
                "how do i begin",
                "where do i begin",
                "explain yourself",
                "introduce yourself",
                "who are you",
                "what are you",
                "what is this",
                "what is this bot",
                "what does this bot do",
                "what does this agent do",
                "what is this agent",
                "what is pricing agent",
                "what is pricing agent",
                "what can this bot do",
                "what can this agent do",
                "how can you help me",
                "how can you help",
                "how can you help us",
                "can you help me",
                "i need help",
                "need help",
                "please help",
                "please help me",
                "stuck",
                "lost",
                "confused",
                "not sure",
                "no idea",
            ) \
                or _re.search(r"\bwhat (can|do|will|should|could) (you|i|we)\b.*(ask|do|say|use|command|handle|answer|support|help|know)\b", s) \
                or _re.search(r"\bhow (can|do|should|to) (i|we|you)\b.*(use|ask|interact|talk|command|query|work|start)\b", s) \
                or _re.search(r"\b(show|list|give|tell).*(command|option|feature|capabilit|what you can|what i can)\b", s) \
                or _re.search(r"\b(command|option|feature|capabilit|example).*(list|all|show|available|support)\b", s) \
                or _re.search(r"\bwhat (question|thing|topic|task).*(can|do|should|could).*(ask|do|try)\b", s) \
                or _re.search(r"\b(yo|hey|hi|hello|hiya|sup|helo|helo).*(what|how|tell|show|help)\b", s) \
                or _re.search(r"\bwhat (all|else|more).*(you|can|do|know|handle|answer|support)\b", s) \
                or _re.search(r"\b(introduce|explain) (yourself|this bot|this agent|what you (do|are|can))\b", s) \
                or _re.search(r"\b(help|guide|assist).*(me|us)?\b", s) and len(s.strip()) < 20:
            say(
                "*ðŸ¤– Pricing Agent â€” What You Can Ask*\n\n"

                "*ðŸ“Š Status & Occupancy*\n"
                "```"
                "show services\n"
                "booking status\n"
                "how many seats booked\n"
                "which seats are booked on 2230\n"
                "which seats are available on 2350\n"
                "how many window seats on 2230\n"
                "show seat layout for 2230\n"
                "fill percentage for each service\n"
                "which service has most bookings today\n"
                "are these real bookings / is this live data"
                "```\n"

                "*ðŸ’° Fare Queries*\n"
                "```"
                "current fares / show fares for 2230\n"
                "min and max fare for 2230\n"
                "fare levels for 2230\n"
                "fare history for 2230\n"
                "show current fares for all services\n"
                "what is the cheapest seat on 2350\n"
                "compare 2230 and 2350"
                "```\n"

                "*ðŸŽ¯ Pricing Intelligence*\n"
                "```"
                "is 2230 correctly priced\n"
                "which services need attention\n"
                "any pricing issues today\n"
                "what classification for 20 seats on friday\n"
                "what tier for 35 seats on wednesday\n"
                "current rule for 2230\n"
                "why is fare high today\n"
                "should I increase fare for 2230"
                "```\n"

                "*ðŸ“Š Analytics*\n"
                "```"
                "fill rate today\n"
                "overall occupancy\n"
                "services with 0 bookings\n"
                "empty buses today\n"
                "services departing tonight\n"
                "services departing in next 4 hours\n"
                "how many services at static fares\n"
                "autoloop status / when does autoloop run"
                "```\n"

                "*âš™ï¸ Apply Pricing Rules*\n"
                "```"
                "apply rules\n"
                "apply rules for 2230\n"
                "act according to rules\n"
                "apply static fares\n"
                "reset static fares\n"
                "reset static fares for 2230\n"
                "price everything correctly\n"
                "check and correct all services"
                "```\n"

                "*ðŸ·ï¸ Change Classification*\n"
                "```"
                "set classification low for 2230\n"
                "set 2230 to super high\n"
                "apply festive pricing to 2230\n"
                "set all services to medium\n"
                "apply ultra high to all active services\n"
                "change pricing model to automation v4 for 2230"
                "```\n"

                "*ðŸ“ˆ Fare Adjustments*\n"
                "```"
                "increase fare by 1 tier for 2230\n"
                "decrease fare by 2 tiers for 2350 OPT\n"
                "set window seat fare to 450 for 2230\n"
                "set last row fare to 299 for 2230\n"
                "set non-window fare to 389 for 2350\n"
                "increase all services by 1 tier\n"
                "drop fares on low-demand services\n"
                "raise fares on high-demand services"
                "```\n"

                "*âš¡ Velocity & Surge*\n"
                "```"
                "booking velocity for 2230\n"
                "check velocity last 30 minutes\n"
                "is there a surge on 2350\n"
                "apply surge if velocity high\n"
                "has velocity increased in last hour"
                "```\n"

                "*ðŸ“… Date-Specific*\n"
                "```"
                "show services tomorrow\n"
                "apply rules for tomorrow\n"
                "show services for 2026-06-05\n"
                "apply pricing for next Friday\n"
                "forecast next 7 days\n"
                "how many seats booked tomorrow\n"
                "services departing in next 2 hours"
                "```\n"

                "*â†©ï¸ Undo*\n"
                "```"
                "undo\n"
                "revert last change\n"
                "rollback\n"
                "restore fares to before surge"
                "```\n"

                "*ðŸ—’ï¸ Notes / Memory*\n"
                "```"
                "remember 2230 notes \"always high demand friday\"\n"
                "recall 2230 notes\n"
                "remember 2350 OPT vip_route true\n"
                "recall 2350 OPT vip_route"
                "```\n"

                "*ðŸ”§ System / Config*\n"
                "```"
                "show route / current route\n"
                "change route to hyderabad to vijayawada\n"
                "pause autoloop / resume autoloop\n"
                "is autoloop running\n"
                "show system status\n"
                "show recent pricing changes / audit log\n"
                "when was last pricing review"
                "```\n"

                "*ðŸ’¬ Conversational*\n"
                "```"
                "give me a summary\n"
                "anything urgent\n"
                "what needs attention today\n"
                "pricing looks wrong on 2230 â€” check it\n"
                "why is 2230 set to low\n"
                "is low correct for sunday with 0 bookings\n"
                "walk me through 2230 pricing logic\n"
                "should I change 2230 to high\n"
                "what happened to 2350 OPT fares"
                "```\n"

                "*ðŸŒ General (no portal needed)*\n"
                "```"
                "explain pricing matrix\n"
                "what is super high classification\n"
                "when does surge activate\n"
                "which day has peak demand\n"
                "what is group A / B / C\n"
                "difference between seater and sleeper pricing\n"
                "what is tier 10\n"
                "how is hours to departure calculated"
                "```\n"

                "_Tip: For any service, you can use just the number â€” e.g. `2230`, `2350 OPT`. The agent resolves it automatically._"
            )
            return

        # ALL PRICING QUERIES -> AI LANE. Agent decides everything.
        # (fast lane only for help, user routes, undo)
        # ─────────────────────────────────────────────────────────────────────
        # ── AI LANE: all pricing decisions, changes, analysis ─────────────────
        print(f"[slack] ðŸ¤– AI handling: {text[:80]}")

        # Send immediate thinking ack â€” user knows agent is working
        _thinking_msg = "â³ Working on it..."
        say(_thinking_msg)

        # Fresh thread per message — prevents Gemini empty reply from history accumulation
        import uuid as _uuid_sl
        from datetime import date as _d_sl, timedelta as _td_sl
        _today_sl = _d_sl.today().strftime("%A, %d %b %Y")

        # Build date context — include target date from this message OR remembered from previous message
        _effective_date = target_date or _last_date.get(user_id)
        _target_str = _effective_date.strftime("%A, %d %b %Y") if _effective_date else ""
        from datetime import datetime as _dt_sl
        _now_sl = _dt_sl.now().strftime("%I:%M %p")
        _date_ctx = f"[Today: {_today_sl} | Now: {_now_sl} IST"
        if _target_str:
            _date_ctx += f" | REQUESTED DATE: {_target_str} — use this date for journey_date in ALL tool calls"
        _date_ctx += "]"
        # Add action reminder so Gemini acts instead of asking questions
        _action_hint = "\nIMPORTANT: Execute immediately. Do NOT ask clarifying questions. Call tools and act."
        _text_with_date = f"{_date_ctx}{_action_hint}\n{text}"
        sid = f"slack-{_uuid_sl.uuid4().hex[:8]}"
        try:
            result = agent.invoke(
                {"messages": [HumanMessage(content=_text_with_date)]},
                config={"configurable": {"thread_id": sid}, "recursion_limit": int(os.environ.get("AGENT_RECURSION_LIMIT", "150"))},
            )
            msgs = result.get("messages") or []
            reply = msgs[-1].content if msgs else ""

            # Retry up to 2x if reply empty
            _max_retries = 2
            for _ri in range(_max_retries):
                _tool_msgs_sl = [m for m in msgs if type(m).__name__ == "ToolMessage"]
                if reply.strip():
                    break  # got a reply — accept it
                if not reply.strip():
                    print(f"[slack] empty reply attempt {_ri+1}/{_max_retries} — retrying")
                    import uuid as _uuid_retry
                    _sid_retry = f"slack-{_uuid_retry.uuid4().hex[:8]}"
                    # Escalating instruction on each retry
                    _retry_texts = [
                        _text_with_date,
                        f"{_text_with_date}\nCRITICAL: You MUST call tools and return a response. Do not return empty.",
                        f"Answer this request using tools: {text}\n{_date_ctx}\nReturn a non-empty response.",
                    ]
                    _retry_r = agent.invoke(
                        {"messages": [HumanMessage(content=_retry_texts[min(_ri, 2)])]},
                        config={"configurable": {"thread_id": _sid_retry}, "recursion_limit": 80},
                    )
                    msgs = _retry_r.get("messages") or []
                    reply = msgs[-1].content if msgs else ""

            # Hallucination guard
            try:
                from guard import check as _hcheck
                h = _hcheck(reply, msgs)
                if h["hallucinated"]:
                    retry = agent.invoke(
                        {"messages": [HumanMessage(
                            content=f"You said you did {h['missing']} but never called the tool. Call it now.")]},
                        config={"configurable": {"thread_id": sid}, "recursion_limit": 40},
                    )
                    msgs = retry.get("messages") or []
                    reply = msgs[-1].content if msgs else reply
            except Exception:
                pass

            # Build block table if pricing tool calls were made
            _pricing_tools = ["set_pricing_model", "static_fare", "bulk_adjust", "reset_static_fare"]
            _all_tool_calls = []
            for _mm in msgs:
                for _tc in getattr(_mm, "tool_calls", []) or []:
                    if _tc.get("name") in _pricing_tools:
                        _all_tool_calls.append(_tc)

            if _all_tool_calls:  # only build block if actual pricing actions taken
                try:
                    from autoloop import _format_slack_blocks
                    from datetime import datetime as _dtnow_sl, date as _d_sl3
                    import route_config as _rc_sl
                    import re as _re_sl2
                    _src_sl, _dst_sl = _get_user_route()

                    # Use requested date (e.g. "04 june") or today for correct service lookup
                    _jd_sl = target_date or _last_date.get(user_id) or _d_sl3.today()

                    # Fetch services directly from Postgres (avoids api_client cache issues)
                    from postgres_reader import get_trips as _pg_trips
                    from api_client import _station_id as _sid_fn
                    _raw_trips = _pg_trips(_sid_fn(_src_sl), _sid_fn(_dst_sl), _jd_sl)
                    _svcs_sl_list = []
                    for _t in _raw_trips:
                        _dep = _t.get("first_boarding")
                        _svcs_sl_list.append({
                            "service_number": _t.get("service_number",""),
                            "trip_id": _t.get("trip_id"),
                            "booked": int(_t.get("booked") or 0),
                            "total_seats": int(_t.get("total_seats") or 45),
                            "classification": _t.get("classification",""),
                            "is_active": bool(_t.get("active", True)),
                            "departure_time": _dep.isoformat() if _dep else "",
                        })
                    _svcs_sl = {str(x.get("trip_id")): x for x in _svcs_sl_list}

                    def _svc_short_name(svc_num):
                        """Extract clean service short name e.g. 0600-1, 2200 OPT"""
                        m = _re_sl2.search(r"(\d{4}(?:-\d+)?(?:\s*OPT)?)\s*$", svc_num, _re_sl2.I)
                        if m: return m.group(1).strip()
                        # fallback: find 4-digit number anywhere
                        m2 = _re_sl2.search(r"\d{4}", svc_num)
                        return m2.group() if m2 else svc_num

                    # Build actions from tool calls
                    _ai_acts = {}
                    for _tc in _all_tool_calls:
                        _tn = _tc.get("name", "")
                        _ta = _tc.get("args", {})
                        _tid = str(_ta.get("trip_id", ""))
                        _svc = _svcs_sl.get(_tid)
                        if not _svc:
                            continue
                        _sn = _svc_short_name(_svc.get("service_number",""))
                        if _sn not in _ai_acts:
                            _ai_acts[_sn] = {
                                "service": _sn,
                                "trip_id": int(_tid) if _tid.isdigit() else _tid,
                                "booked": int(_svc.get("booked") or 0),
                                "total_seats": int(_svc.get("total_seats") or 45),
                                "current_cls": _svc.get("classification", ""),
                                "target_cls": _ta.get("classification", ""),
                                "velocity": 0, "done": [], "skipped": [],
                            }
                        if _tn == "set_pricing_model":
                            _prev = (_ta.get("current_classification") or "").strip()
                            _new  = (_ta.get("classification") or "").strip()
                            # Skip if no real change
                            if _new and _new.lower() != _prev.lower():
                                _ai_acts[_sn]["done"].append(f"{_prev} -> {_new}" if _prev else _new)
                            else:
                                _ai_acts[_sn]["skipped"].append(f"already {_new or _prev}")
                        elif _tn == "static_fare":
                            _ai_acts[_sn]["done"].append(f"static fare Rs.{_ta.get('fare','')}")
                        elif _tn == "bulk_adjust":
                            _adj = _ta.get("adjustment_id", "")
                            if _adj != "":
                                _ai_acts[_sn]["done"].append(f"fare adj {_adj}%")
                        elif _tn == "reset_static_fare":
                            _ai_acts[_sn]["done"].append("static fares reset")

                    # Add unchanged services (reuse stored list — no extra API call)
                    for _svc in _svcs_sl_list:
                        if not _svc.get("is_active", True):
                            continue
                        _sn2 = _svc_short_name(_svc.get("service_number",""))
                        if _sn2 not in _ai_acts:
                            _ai_acts[_sn2] = {
                                "service": _sn2,
                                "trip_id": int(_svc.get("trip_id") or 0),
                                "booked": int(_svc.get("booked") or 0),
                                "total_seats": int(_svc.get("total_seats") or 45),
                                "current_cls": _svc.get("classification",""),
                                "target_cls": _svc.get("classification",""),
                                "velocity": 0, "done": [], "skipped": ["no change needed"],
                            }

                    _act_list = list(_ai_acts.values())
                    # Only send block if at least one service had actual change
                    _any_change = any(a.get("done") for a in _act_list)
                    if not _any_change:
                        # No changes — send simple text reply instead of block
                        say(f"🤖 {reply or 'No pricing changes needed.'}")
                    else:
                        _ts_sl  = _dtnow_sl.now().strftime("%I:%M %p")
                        _dl_sl  = _jd_sl.strftime("%A, %d %b %Y")
                        _blocks_sl = _format_slack_blocks(_act_list, _ts_sl, _dl_sl, _src_sl, _dst_sl)
                        if _blocks_sl:
                            _blocks_sl[0]["text"]["text"] = _blocks_sl[0]["text"]["text"].replace(
                                "Pricing Review", "AI Pricing")
                        say(msg=f"AI Pricing — {_ts_sl} | {_dl_sl}", blocks=_blocks_sl)
                except Exception as _be:
                    print(f"[slack] block format error: {_be}")
                    say(f"🤖 {reply or 'Done.'}")
            else:
                say(f"🤖 {reply or 'Done. No changes needed.'}")

        except Exception as e:
            err = str(e).lower()
            if any(w in err for w in ("rate", "429", "quota")):
                # groq_chat already retried 4x â€” all attempts exhausted
                say("â¸ AI rate limit reached. Pricing rules and status queries still work â€” just ask normally.")
            else:
                say(f"âš ï¸ Error: {str(e)[:200]}")

    return handle


def _loop(agent):
    bot = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    app_t = os.environ.get("SLACK_APP_TOKEN", "").strip()
    if not bot.startswith("xoxb-") or not app_t.startswith("xapp-"):
        print("[slack] tokens missing â€” listener disabled")
        return
    import re
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    app = App(token=bot)
    handle = _build_handle(agent)

    @app.event("message")
    def on_msg(event, say):
        if event.get("channel_type") == "im" and "bot_id" not in event:
            ts = event.get("thread_ts") or event.get("ts")
            handle(event.get("text", ""), say,
                   user_id=event.get("user", "default"), thread_ts=ts)

    @app.event("app_mention")
    def on_mention(event, say):
        txt = re.sub(r"<@\w+>", "", event.get("text", "")).strip()
        ts = event.get("thread_ts") or event.get("ts")
        handle(txt, say, user_id=event.get("user", "default"), thread_ts=ts)

    print("[slack] listener starting")
    try:
        handler = SocketModeHandler(app, app_t)
        handler.connect()
        print("[slack] listener connected")
        while True:
            time.sleep(1)
    except Exception as e:
        print(f"[slack] connection error: {e}")


def start(agent):
    global _started
    _load_undo_from_db()
    with _lock:
        if _started:
            return
        _started = True
    _agent_ref["agent"] = agent
    t = threading.Thread(target=_loop, args=(agent,), daemon=True, name="slack-listener")
    t.start()
