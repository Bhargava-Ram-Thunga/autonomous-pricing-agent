"""LangGraph ReAct agent — Gemini only."""
import os
from langchain_core.messages import SystemMessage

try:
    from langgraph.checkpoint.postgres import PostgresSaver
except ImportError:
    PostgresSaver = None
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from api_tools import PRICING_TOOLS as TOOLS  # lean tool set — fewer tokens
from system_prompt import SYSTEM_PROMPT


def build_agent():
    # ── Gemini (via OpenAI-compatible endpoint) ───────────────────────────────
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")

    from gemini_chat import build as build_gemini
    llm = build_gemini()
    print(f"[agent] LLM: Gemini {os.environ.get('GEMINI_MODEL','gemini-2.5-flash-lite')}")

    # Claude handles conversation history well — MemorySaver for clean sessions
    memory = MemorySaver()
    print("[agent] memory: in-memory (fresh context per session)")

    # ── Inject today's date ────────────────────────────────────────────────
    from datetime import date
    _today  = date.today().strftime("%A, %d %b %Y")
    _prompt = SYSTEM_PROMPT.replace("{TODAY}", _today)

    agent = create_react_agent(
        llm,
        TOOLS,
        prompt=SystemMessage(content=_prompt),
        checkpointer=memory,
    )
    print(f"[agent] ✅ Ready — {len(TOOLS)} tools | today={_today}")
    return agent
