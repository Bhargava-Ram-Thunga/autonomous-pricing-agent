"""Find working refresh endpoint."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
import requests, os

BASE_URL = os.environ.get("API_BASE_URL", "https://api-stage.example-portal.com/admin")
session = requests.Session()
session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

resp = session.post(f"{BASE_URL}/auth/login", json={
    "email": os.environ["PORTAL_USER"],
    "password": os.environ["PORTAL_PASS"],
    "deviceId": "pricing-agent",
})
refresh_token = None
for cookie in resp.cookies:
    if cookie.name == "refresh_token":
        refresh_token = cookie.value
print(f"refresh_token (first 40): {refresh_token[:40] if refresh_token else None}")

# Try all common refresh endpoints
endpoints = [
    ("POST", "/auth/refresh-token"),
    ("POST", "/auth/refreshToken"),
    ("POST", "/auth/token"),
    ("GET",  "/auth/refresh-token"),
    ("POST", "/auth/access-token"),
]

for method, path in endpoints:
    try:
        if method == "POST":
            r = session.post(f"{BASE_URL}{path}", json={"refreshToken": refresh_token})
        else:
            r = session.get(f"{BASE_URL}{path}")
        print(f"  {method} {path} -> {r.status_code} | {r.text[:80]}")
    except Exception as e:
        print(f"  {method} {path} -> ERROR {e}")
