"""Test pricing analyst questions against the fast-lane + live API."""
import sys, os, time, re
sys.path.insert(0, r"C:\Users\Vasanth\Desktop\Pricing Agent LG")
os.chdir(r"C:\Users\Vasanth\Desktop\Pricing Agent LG")
from dotenv import load_dotenv
load_dotenv()

from datetime import date as _d, timedelta as _td

QUESTIONS = [
    # Occupancy / status
    ("how many seats are booked today",         "booking-status"),
    ("what is the current occupancy",           "booking-status"),
    ("status of 2230",                          "booking-status"),
    ("total bookings across all services",      "booking-status"),
    # Services
    ("list services",                           "list-services"),
    ("show me all services today",              "list-services"),
    ("show services for tomorrow",              "date-query"),
    ("show services for 2026-05-30",            "date-query"),
    ("show services for next week",             "date-query"),
    # Fares
    ("show current fares",                      "show-fares"),
    ("what are the fares on 2230",              "show-fares"),
    ("what is the fare range",                  "show-fares"),
    # Rules
    ("what are the pricing rules",              "rules"),
    ("show pricing matrix",                     "rules"),
    ("explain the rules",                       "rules"),
    # Apply pricing
    ("act according to rules",                  "apply-rules"),
    ("apply pricing rules",                     "apply-rules"),
    ("do pricing for today",                    "apply-rules"),
    ("apply rules for tomorrow",                "apply-rules"),
    ("follow the matrix",                       "apply-rules"),
    ("price according to matrix",               "apply-rules"),
    # Forecast
    ("forecast 3 days",                         "forecast"),
    ("show upcoming 7 days",                    "forecast"),
    # Route
    ("what is the current route",               "route"),
    ("show route",                              "route"),
    # Data validity
    ("is this today's data",                    "today-check"),
    ("is this real data",                       "today-check"),
    # AI-only (should NOT match fast lane)
    ("why is 2230 still on Super Low",          "AI-LANE"),
    ("should i increase fares on 2350",         "AI-LANE"),
    ("compare today vs yesterday",              "AI-LANE"),
    ("which service needs attention",           "AI-LANE"),
    ("increase fare on 2230 by 50 rupees",      "AI-LANE"),
]

def classify_fast_lane(q):
    s = q.lower()
    today = _d.today()

    if re.search(r"\b(what|show|explain|tell|describe|give|how).*(rule|matrix|pricing rule|fare rule)\b", s) \
            or re.search(r"\b(explain|describe)\b.*(rule|pricing|fare|matrix)\b", s) \
            or re.search(r"\bwhat are\b.*(rule|pricing|fare|matrix)\b", s) \
            or re.search(r"\bthe rule[s]?\b", s) \
            or s.strip() in ("rules","pricing rules","what are the rules","show rules",
                             "pricing matrix","show pricing matrix","the rules","explain rules",
                             "what are pricing rules","what are the pricing rules"):
        return "rules"

    if re.search(r"\b(apply|run|change|update|set|fix|act|do|execute|follow|use)\b.*(rule|pricing|fare|classif|matrix)", s) \
            or re.search(r"\baccording to\b.*(rule|matrix|pricing)", s) \
            or re.search(r"\b(pricing|fare).*(rule|matrix|correct|right|now)\b", s) \
            or s.strip() in ("apply rules","run pricing","apply pricing","price now","update fares",
                             "act","do pricing","price it","price them","follow rules","use rules"):
        return "apply-rules"

    if re.search(r"\b(is this|are these|is it|this is)\b.*(today|real|correct|right|actual|live|current)", s) \
            or re.search(r"\b(today|real|live).*(data|booking|service|price|fare)\b", s):
        return "today-check"

    if s.strip() in ("route","current route","what route","show route",
                     "what is the current route","current route?"):
        return "route"

    # Date parsing happens first (before list-services)
    has_date = ("tomorrow" in s or "next week" in s or re.search(r"in\s+\d+\s+day", s)
                or re.search(r"\b\d{4}-\d{2}-\d{2}\b", q))
    if has_date and any(w in s for w in ("service","book","occup","trip","fare","show","list","check")):
        return "date-query"

    if any(w in s for w in ("list","show","what")) and "service" in s \
            and not any(w in s for w in ("increase","decrease","adjust","change","set","apply")):
        return "list-services"

    if re.search(r"\b(how many|count|total)\b.*\b(book|seat|occup|ticket)\b", s) \
            or re.search(r"\b(book|occup|status)\b.*\b(2[23]\d{2}|service)\b", s) \
            or re.search(r"\b(current|what).*(occup|booking|booked|seats?\s+book)\b", s) \
            or re.search(r"\b(occup|booked|booking).*(today|now|current)\b", s) \
            or re.search(r"\btotal\b.*(booking|seat|occup|service)\b", s) \
            or re.search(r"\b(current|what).*(occupancy|occup)\b", s) \
            or s.strip() in ("status","bookings","occupancy","seats booked","how many booked",
                             "total bookings","current occupancy"):
        return "booking-status"

    if any(w in s for w in ("forecast","upcoming")) and any(w in s for w in ("day","days","week")):
        return "forecast"

    if any(w in s for w in ("show","read","current","what")) and "fare" in s \
            and not any(w in s for w in ("increase","decrease","adjust","change","set","apply")):
        return "show-fares"

    return "AI-LANE"


PASS = 0
FAIL = 0
AI_COUNT = 0

print(f"\n{'Q':<45} {'EXPECTED':<15} {'GOT':<15} {'RESULT'}")
print("-" * 90)

for q, expected in QUESTIONS:
    got = classify_fast_lane(q)
    if expected == "AI-LANE":
        ai_ok = (got == "AI-LANE")
        status = "OK" if ai_ok else "FAIL(should->AI)"
        if ai_ok: AI_COUNT += 1
        else: FAIL += 1
    else:
        ok = (got == expected)
        status = "OK" if ok else f"FAIL"
        if ok: PASS += 1
        else: FAIL += 1
    flag = "OK" if "OK" in status else "!!"
    print(f"{flag} {q:<43} {expected:<15} {got:<15} {status}")

print(f"\n{'='*90}")
print(f"Fast-lane coverage: {PASS}/{len([x for x in QUESTIONS if x[1] != 'AI-LANE'])} questions routed correctly without AI")
print(f"AI isolation:       {AI_COUNT}/{len([x for x in QUESTIONS if x[1] == 'AI-LANE'])} complex questions correctly sent to AI")
print(f"Failures:           {FAIL}")
print(f"{'='*90}\n")
