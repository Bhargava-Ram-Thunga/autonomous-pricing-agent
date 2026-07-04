import sys; sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
from pricing_rules import (
    needs_reclassification, can_reprice, mark_repriced,
    cooldown_remaining, clamp_fare, matrix_classification,
    proximity_tier_boost, upgrade_tier
)
from datetime import datetime, timedelta

print("--- Idempotency ---")
print("already at target (skip):", not needs_reclassification("Super_Low", "super low"))
print("needs change:            ", needs_reclassification("Medium", "high"))

print("\n--- Cooldown ---")
print("fresh trip, can reprice: ", can_reprice(99999))
mark_repriced(99999)
print("just repriced, blocked:  ", not can_reprice(99999))
print("remaining (sec):         ", cooldown_remaining(99999))

print("\n--- Fare guardrails ---")
print("250 -> clamped to:", clamp_fare(250))
print("999 -> unchanged: ", clamp_fare(999))
print("3000 -> clamped:  ", clamp_fare(3000))

print("\n--- Pricing matrix ---")
for n in [2, 7, 15, 22, 30, 37, 42]:
    print(f"  booked={n:2d} -> {matrix_classification(n) or 'static fares'}")

print("\n--- Departure proximity boost ---")
in_4h  = datetime.now() + timedelta(hours=4)
in_20h = datetime.now() + timedelta(hours=20)
in_3d  = datetime.now() + timedelta(days=3)
print(f"  departs in 4h:  +{proximity_tier_boost(in_4h)} tiers  -> e.g. low -> {upgrade_tier('low', proximity_tier_boost(in_4h))}")
print(f"  departs in 20h: +{proximity_tier_boost(in_20h)} tier   -> e.g. low -> {upgrade_tier('low', proximity_tier_boost(in_20h))}")
print(f"  departs in 3d:  +{proximity_tier_boost(in_3d)} tiers  -> no boost")
