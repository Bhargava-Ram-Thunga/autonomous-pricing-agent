"""Test full autoloop cycle — pricing actions + summary."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
from autoloop import _fetch_real_data, _apply_pricing, _plain_summary

print("Fetching live data...")
svcs, velocity_map, date_label = _fetch_real_data()
print(f"Found {len(svcs)} services | {date_label}\n")

print("Applying pricing rules...")
actions = _apply_pricing(svcs, velocity_map)

print("\n--- ACTIONS ---")
for a in actions:
    print(f"  {a['service']}: booked={a['booked']} | {a['current_cls']} -> {a['target_cls'] or 'static'} | done={a['done']} | skipped={a['skipped']}")

print("\n--- SLACK SUMMARY (built-in) ---")
print(_plain_summary(actions))
