"""Probe refresh token endpoint and response structure."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
import requests, os, json

BASE_URL = os.environ.get("API_BASE_URL", "https://api-stage.example-portal.com/admin")
session = requests.Session()
session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

# Step 1: login — capture ALL cookies
resp = session.post(f"{BASE_URL}/auth/login", json={
    "email": os.environ["PORTAL_USER"],
    "password": os.environ["PORTAL_PASS"],
    "deviceId": "pricing-agent",
})
print(f"Login status: {resp.status_code}")
print(f"All cookies: {dict(resp.cookies)}")
try:
    body = resp.json()
    print(f"Body keys: {list(body.keys()) if isinstance(body, dict) else type(body)}")
    # print relevant fields only
    for k in ("access_token","refresh_token","token","expiresIn","expires_in","tokenType"):
        if k in (body if isinstance(body, dict) else {}):
            print(f"  {k}: {str(body[k])[:60]}")
except Exception as e:
    print(f"Body parse error: {e}")

# Step 2: try common refresh endpoints
access = None
refresh = None
for cookie in resp.cookies:
    print(f"  cookie name={cookie.name} expires={cookie.expires}")
    if cookie.name == "access_token": access = cookie.value
    if cookie.name == "refresh_token": refresh = cookie.value

if refresh:
    print(f"\nFound refresh_token — trying /auth/refresh...")
    r2 = session.post(f"{BASE_URL}/auth/refresh", json={"refreshToken": refresh})
    print(f"  /auth/refresh status: {r2.status_code}")
    if r2.status_code == 200:
        print(f"  response: {r2.text[:200]}")

    r3 = session.post(f"{BASE_URL}/auth/token/refresh", json={"refresh_token": refresh})
    print(f"  /auth/token/refresh status: {r3.status_code}")
else:
    print("\nNo refresh_token cookie found — API may not use refresh tokens")
    # Try GET refresh with just the session cookie
    r2 = session.get(f"{BASE_URL}/auth/refresh")
    print(f"  GET /auth/refresh status: {r2.status_code}")
    r3 = session.post(f"{BASE_URL}/auth/refresh", json={})
    print(f"  POST /auth/refresh status: {r3.status_code} | {r3.text[:100]}")
