"""Advanced pricing analyst questions — multi-service strategy, elasticity, surge, competitive."""
import sys, os, time
sys.path.insert(0, r"C:\Users\Vasanth\Desktop\Pricing Agent LG")
os.chdir(r"C:\Users\Vasanth\Desktop\Pricing Agent LG")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()

from agent import build_agent
from langchain_core.messages import HumanMessage

print("Building agent...")
agent = build_agent()
print("Agent ready.\n")

QUESTIONS = [
    ("Q1: Multi-service surge strategy",
     "We have 3 services tonight: 2230 at 60% fill, 2350 OPT at 15% fill, 0015 at 5% fill. "
     "Booking velocity on 2230 is 45/hr, 2350 OPT is 8/hr, 0015 is 0/hr. "
     "Recommend a differentiated pricing action for each service right now. "
     "Which should get a surge boost, which should stay, which should drop?"),

    ("Q2: Festive weekend demand spike",
     "This Friday and Saturday are a long weekend — Bangalore to Tirupati bookings historically spike 3x. "
     "We currently have all services on Automation v4 with Medium classification. "
     "Should I pre-emptively move to Festive classification today (Thursday)? "
     "What is the risk of moving too early vs too late? Give a step-by-step plan."),

    ("Q3: Competitor fare undercut",
     "A competitor just dropped their Bangalore-Tirupati fare to ₹299 flat. "
     "Our current window seat fare is ₹390 on Super Low. Fill rate is 20% with 6 hours to departure. "
     "Should we match, undercut, or hold? What is the revenue impact of each option? "
     "At what fill rate does it no longer make sense to drop fares?"),

    ("Q4: Dynamic surge + proximity combined",
     "Service 2230 departs in 4 hours. Currently 28/43 seats booked (High classification). "
     "Booking velocity spiked to 52/hr in the last 30 minutes. "
     "Our rules say: velocity >30 → bulk_adjust, departure <6h → +2 tiers. "
     "But we're already at High. Should we go Super High + Ultra High? "
     "What is the maximum fare we can charge without killing conversion? "
     "Walk me through the exact actions to take."),

    ("Q5: Revenue recovery after bad night",
     "Last night both services ran at 8% fill (7/86 seats). Total revenue was ₹2,450. "
     "Tonight same pattern is emerging — 4/86 seats at 8 PM, 3 hours to first departure. "
     "What went wrong in pricing last night? "
     "What specific actions should we take RIGHT NOW to avoid repeating it? "
     "Include fare levels, classifications, and timing."),

    ("Q6: Seat-type pricing optimisation",
     "Service 2350 OPT has 43 seats: 20 window, 18 non-window, 5 last-row. "
     "Currently all at static fares (window=349, non-window=329, last-row=299). "
     "12 window seats booked, 2 non-window booked, 0 last-row booked. "
     "Should we raise window seat fares since demand is higher there? "
     "What differential pricing strategy maximises total revenue across all seat types?"),

    ("Q7: Empty bus risk management",
     "It is 10 PM. Service 2230 departs at 11:25 PM with only 1 seat booked out of 43. "
     "The bus will run regardless (fixed cost committed). "
     "At what fare level does taking additional passengers become revenue-positive? "
     "Should we drop to ₹199 or below breakeven to maximise occupancy? "
     "What is the minimum viable fare for a last-minute fill strategy?"),

    ("Q8: Weekly pattern analysis",
     "Looking at the last 7 days: Mon-Wed average fill 65%, Thu 45%, Fri-Sat 82%, Sun 38%. "
     "Our current system uses same pricing rules for all days. "
     "How should we differentiate pricing by day of week? "
     "Specifically: which days need lower base fares, which need higher, "
     "and at what booking thresholds should tiers be different on weekdays vs weekends?"),
]

for title, q in QUESTIONS:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    print(f"Q: {q}\n")

    t0 = time.time()
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=q)]},
            config={"configurable": {"thread_id": f"test2_{title[:15]}"}, "recursion_limit": 40},
        )
        msgs = result.get("messages", [])
        reply = msgs[-1].content if msgs else "(no reply)"
        elapsed = int((time.time() - t0) * 1000)

        tools_used = []
        for m in msgs:
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    tools_used.append(tc.get("name","?"))

        print(f"A ({elapsed}ms | tools: {tools_used or 'none'}):")
        print(reply)

    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"ERROR ({elapsed}ms): {e}")

    time.sleep(4)

print("\nDone.")
