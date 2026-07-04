"""Verify GET /auth/refresh-token returns new access_token."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
import requests, os, time

BASE_URL = os.environ.get("API_BASE_URL", "https://api-stage.example-portal.com/admin")
session = requests.Session()
session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

# Login
resp = session.post(f"{BASE_URL}/auth/login", json={
    "email": os.environ["PORTAL_USER"],
    "password": os.environ["PORTAL_PASS"],
    "deviceId": "pricing-agent",
})
old_access = None
for c in resp.cookies:
    if c.name == "access_token": old_access = c.value
print(f"access_token after login (last 20): ...{old_access[-20:] if old_access else None}")

# Call refresh endpoint
r = session.get(f"{BASE_URL}/auth/refresh-token")
print(f"\nGET /auth/refresh-token -> {r.status_code}")
print(f"Response body: {r.text[:200]}")
print(f"Response cookies: {dict(r.cookies)}")

new_access = None
for c in r.cookies:
    print(f"  cookie: name={c.name} expires={c.expires}")
    if c.name == "access_token": new_access = c.value

if new_access:
    print(f"\nnew access_token (last 20): ...{new_access[-20:]}")
    print(f"tokens differ: {old_access != new_access}")
    # Verify new token works
    session.headers.update({"Authorization": f"Bearer {new_access}"})
    test = session.get(f"{BASE_URL}/services/trips", params={"journeyDate": "2026-05-29", "sourceId": 7, "destinationId": 12})
    print(f"API call with new token: {test.status_code}")
else:
    print("No new access_token in response cookies")
    # Maybe refresh token is sent as cookie automatically — check if session cookie updated
    print(f"Session cookies now: {dict(session.cookies)}")
