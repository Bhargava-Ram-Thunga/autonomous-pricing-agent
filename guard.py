"""Hallucination guard.
Detect: agent reply CLAIMS action (e.g. 'increased fares') but no matching
tool_call was made in this turn. Retry agent with a reminder if detected.
"""
import re

# Patterns that strongly indicate the LLM claimed to do an action.
# IMPORTANT: only match phrases that cannot appear in a normal business summary.
# Removed r"\b[+\-]\d+\b" — too broad, fires on every valid delta report.
ACTION_VERBS = {
    "bulk_adjust": [
        r"\bbulk\s*adjust(?:ment)?\s+applied\b",
        r"\bapplied\s+(?:fare\s+)?adjustment\b",
        r"\bfare\s+(?:increased|decreased)\s+by\s+₹",
    ],
    "static_fare": [
        r"\bstatic\s*fare[s]?\s+(?:set|applied|done)\b",
        r"\bset\s+(?:exact\s+)?fare[s]?\s+on\s+seats?\b",
    ],
    "set_pricing_model": [
        r"\bclassification\s+(?:changed|updated|set)\s+to\s+[A-Z]",
        r"\bpricing\s+model\s+(?:changed|updated|set)\s+to\s+\w",
    ],
}


def detect_claimed_actions(text: str) -> set[str]:
    """Return set of tool names the reply text claims to have performed."""
    if not text:
        return set()
    t = text.lower()
    out = set()
    for tool_name, pats in ACTION_VERBS.items():
        for p in pats:
            if re.search(p, t, re.I):
                out.add(tool_name)
                break
    return out


def detect_made_calls(messages: list) -> set[str]:
    """Return set of tool names actually called in this turn."""
    out = set()
    for m in messages:
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name:
                    out.add(name)
    return out


def check(reply: str, messages: list) -> dict:
    """Return {hallucinated: bool, claimed: set, called: set, missing: set}."""
    claimed = detect_claimed_actions(reply)
    called = detect_made_calls(messages)
    missing = claimed - called
    return {
        "hallucinated": bool(missing),
        "claimed": list(claimed),
        "called": list(called),
        "missing": list(missing),
    }
