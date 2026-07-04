"""Test autoloop data fetch + prompt — verify real numbers before running full agent."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
from autoloop import _fetch_real_data, _build_prompt

print("Fetching real data...")
svcs, velocity_map = _fetch_real_data()

print(f"\nFound {len(svcs)} services:")
for s in svcs:
    sn  = s.get("service_number","")
    tid = s.get("trip_id","")
    bkd = s.get("booked",0)
    cls = s.get("classification","?")
    print(f"  {sn} | trip_id={tid} | booked={bkd} | class={cls}")

print("\n--- PROMPT THAT WILL BE SENT TO LLM ---")
print(_build_prompt(svcs, velocity_map))
