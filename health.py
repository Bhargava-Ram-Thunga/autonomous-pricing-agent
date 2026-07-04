"""Health monitoring: heartbeat + crash alerts → Slack."""
import os
import sys
import time
import threading
import traceback


def _slack_post(text: str):
    try:
        from slack_sdk import WebClient
        bot = os.environ.get("SLACK_BOT_TOKEN", "")
        ch = os.environ.get("SLACK_CHANNEL", "")
        if bot.startswith("xoxb-") and ch:
            WebClient(token=bot).chat_postMessage(channel=ch, text=text)
    except Exception as e:
        print(f"[health slack fail] {e}")


def install_crash_handler():
    """Catch uncaught exceptions in main thread + sys.excepthook."""
    original = sys.excepthook

    def handler(exc_type, exc_value, exc_tb):
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))[-1500:]
        _slack_post(f"💥 CRASH:\n```{tb}```")
        original(exc_type, exc_value, exc_tb)

    sys.excepthook = handler

    # Threading exceptions
    def thread_handler(args):
        tb = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))[-1500:]
        _slack_post(f"💥 THREAD CRASH ({args.thread.name}):\n```{tb}```")

    threading.excepthook = thread_handler
    print("[health] crash handler installed")


def start_heartbeat(interval_sec: int = 600):
    """Post 'alive' message every interval_sec seconds."""
    if interval_sec <= 0:
        return

    def _beat():
        time.sleep(interval_sec)
        while True:
            try:
                from worker import _HISTORY
                services = len(_HISTORY)
                _slack_post(f"💚 alive. services tracked: {services}")
            except Exception as e:
                print(f"[heartbeat fail] {e}")
            time.sleep(interval_sec)

    t = threading.Thread(target=_beat, daemon=True, name="heartbeat")
    t.start()
    print(f"[health] heartbeat every {interval_sec}s")


def alert(level: str, msg: str):
    """Manual alert: level in {info, warn, error}."""
    emoji = {"info": "ℹ️", "warn": "⚠️", "error": "🚨"}.get(level, "•")
    _slack_post(f"{emoji} {msg}")
