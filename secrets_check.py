"""Startup secrets validation.
Checks required and optional env vars on boot. Call validate() from main.py.
"""
import os
import sys
import io

# Windows cp1252 terminals can't print emojis — wrap stdout safely
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# (var_name, required, description)
_SECRETS = [
    ("GROQ_API_KEY",       True,  "Groq LLM API key — agent cannot run without this"),
    ("PORTAL_USER",        True,  "PricingCo portal login username"),
    ("PORTAL_PASS",        True,  "PricingCo portal password"),
    ("API_BASE_URL",       True,  "PricingCo API base URL"),
    ("SLACK_BOT_TOKEN",    True,  "Slack bot token (xoxb-...) — all Slack features disabled without this"),
    ("SLACK_APP_TOKEN",    True,  "Slack app token (xapp-...) — Socket Mode disabled without this"),
    ("SLACK_CHANNEL",      True,  "Slack channel ID for autoloop messages"),
    ("POSTGRES_URI",       True,  "Postgres connection URI — undo/remember/recall lost on restart without this"),
    ("AUTOLOOP_SEC",       False, "Autoloop interval in seconds (0 = disabled)"),
    ("AGENT_API_KEY",      False, "API key for /chat endpoints (leave empty for open access in dev)"),
    ("HF_TOKEN",           False, "HuggingFace token — needed for LLM fallback on Groq rate limit"),
    ("HEARTBEAT_SEC",      False, "Heartbeat interval seconds (0 = disabled)"),
    ("LOG_DIR",            False, "Log directory path (default: logs/)"),
]


def validate(exit_on_missing: bool = False) -> bool:
    missing_required = []
    missing_optional = []

    for var, required, desc in _SECRETS:
        val = os.environ.get(var, "").strip()
        if not val:
            if required:
                missing_required.append((var, desc))
            else:
                missing_optional.append((var, desc))

    # Format warnings
    warnings = []
    bot = os.environ.get("SLACK_BOT_TOKEN", "")
    app = os.environ.get("SLACK_APP_TOKEN", "")
    if bot and not bot.startswith("xoxb-"):
        warnings.append("SLACK_BOT_TOKEN should start with 'xoxb-'")
    if app and not app.startswith("xapp-"):
        warnings.append("SLACK_APP_TOKEN should start with 'xapp-'")

    ok = not missing_required

    if missing_required:
        print("\n" + "=" * 60)
        print("🔴 MISSING REQUIRED SECRETS — agent will not function correctly:")
        for var, desc in missing_required:
            print(f"   ✗ {var:<30}  {desc}")
        print("   Add these to your .env file and restart.")
        print("=" * 60 + "\n")

    if warnings:
        print("⚠️  Secret format warnings:")
        for w in warnings:
            print(f"   ! {w}")

    if missing_optional:
        print("ℹ️  Optional secrets not set (some features limited):")
        for var, desc in missing_optional:
            print(f"   - {var:<30}  {desc}")

    if ok and not missing_optional and not warnings:
        print("✅ All secrets OK")

    if not ok and exit_on_missing:
        sys.exit(1)

    return ok


def check_rotation_reminder():
    """Warn if secrets haven't been rotated in >90 days."""
    from pathlib import Path
    from datetime import datetime
    marker = Path("data/.secret_rotation_ts")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        if marker.exists():
            last = datetime.fromisoformat(marker.read_text().strip())
            age_days = (datetime.now() - last).days
            if age_days > 90:
                print(f"⚠️  Secrets last rotated {age_days} days ago. "
                      f"Consider rotating GROQ_API_KEY, PORTAL_PASSWORD, SLACK tokens.")
        else:
            marker.write_text(datetime.now().isoformat())
    except Exception:
        pass
