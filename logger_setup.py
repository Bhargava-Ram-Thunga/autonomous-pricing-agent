"""Centralized logging — file + console. Import once from main.py."""
import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(os.environ.get("LOG_DIR", "logs"))
LOG_DIR.mkdir(exist_ok=True)

def setup():
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console — INFO and above
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File — rotating, 5 MB × 5 files — ALL levels
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "pricing_agent.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Separate audit log — every fare write action
    audit_fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "audit.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    audit_fh.setLevel(logging.INFO)
    audit_fh.setFormatter(fmt)
    logging.getLogger("audit").addHandler(audit_fh)
    logging.getLogger("audit").propagate = True

def audit(action: str, trip_id, service: str, details: str):
    logging.getLogger("audit").info(
        f"action={action} | trip={trip_id} | service={service} | {details}"
    )
