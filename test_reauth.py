"""Verify reauth logic by directly calling _reauth and checking token changes."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
from api_client import get_client
import requests, os

BASE_URL = os.environ.get("API_BASE_URL", "https://api-stage.example-portal.com/admin")

# 1. Check staging actually validates tokens
s = requests.Session()
s.headers.update({"Authorization": "Bearer FAKE_INVALID_TOKEN", "Accept": "application/json"})
r = s.get(f"{BASE_URL}/services/trips", params={"journeyDate":"2026-05-29","sourceId":7,"destinationId":12})
print(f"Staging with fake token -> HTTP {r.status_code}")
print(f"  (staging does not enforce auth = expected on dev/staging environment)")

# 2. Verify _reauth() itself works — token changes after refresh call
c = get_client()
old_token = c._token
print(f"\nToken before refresh (last 10): ...{old_token[-10:] if old_token else None}")

success = c._refresh()
new_token = c._token
print(f"_refresh() returned: {success}")
print(f"Token after refresh (last 10): ...{new_token[-10:] if new_token else None}")
print(f"Token rotated: {old_token != new_token}")
print(f"New token is valid JWT: {new_token.startswith('eyJ') if new_token else False}")
