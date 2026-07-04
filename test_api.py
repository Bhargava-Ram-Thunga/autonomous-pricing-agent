import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
from api_client import get_client

c = get_client()
c.search_services("BANGALORE", "TIRUPATI")
svcs = c.list_services()
print(f"BLR->TPT services: {len(svcs)}")
for s in svcs:
    print(f"  {s['service_number']} | trip_id={s['trip_id']} | booked={s['booked']} | class={s['classification']}")
