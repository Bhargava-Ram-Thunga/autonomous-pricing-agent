"""Test complex pricing analyst questions through the AI agent directly."""
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
    ("Q1: Late-night low occupancy",
     "It is 9 PM. Both active services tonight (2230 and 2350 OPT) have only 2 seats booked out of 43. "
     "They depart at 11:25 PM and 11:50 PM IST. What pricing action do you suggest to maximise revenue "
     "in the next 2 hours before departure?"),

    ("Q2: Proximity + occupancy decision",
     "Service 2350 OPT departs in less than 3 hours with 2/43 seats booked and currently on Super_Low. "
     "Should I keep static fares, upgrade the classification, or do something else? Give your recommendation."),

    ("Q3: Low velocity scenario",
     "Booking velocity on 2230 is 0 bookings per hour for the last 2 hours. The service departs in 2.5 hours "
     "with 2 seats filled. Should I reduce fares to drive last-minute bookings or hold price? "
     "What is the industry-standard approach?"),

    ("Q4: Revenue vs occupancy tradeoff",
     "Tonight we have 2 services with 4 total bookings out of 86 available seats (5% fill rate). "
     "Is it better to drop fares to fill more seats, or hold current pricing and accept low occupancy? "
     "What is the breakeven point?"),

    ("Q5: Classification mismatch",
     "2230 shows Super_Low classification but has Automation_v4 model. The pricing rules say 2 bookings "
     "should use static fares (window=349, non-window=329, last-row=299). "
     "Is there a conflict? What should be the correct state?"),
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
            config={"configurable": {"thread_id": f"test_{title[:10]}"}, "recursion_limit": 40},
        )
        msgs = result.get("messages", [])
        reply = msgs[-1].content if msgs else "(no reply)"
        elapsed = int((time.time() - t0) * 1000)

        # Count tool calls
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

    time.sleep(3)

print("\nDone.")
