"""FastAPI server exposing the LangGraph pricing agent."""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import uuid
import json
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

load_dotenv()
import logger_setup
logger_setup.setup()
import secrets_check
secrets_check.validate()
secrets_check.check_rotation_reminder()

from agent import build_agent

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def _require_api_key(key: str = Security(_API_KEY_HEADER)):
    expected = os.environ.get("AGENT_API_KEY", "")
    if not expected:
        return  # no key configured → open (dev mode)
    if key != expected:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid API key")

_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    from slack_listener import start as start_slack
    import route_config
    try:
        route_config.load_from_db()
    except Exception as e:
        print(f"[route] DB load failed ({e}), using default route")
    print(f"[route] active: {route_config.source} -> {route_config.destination}")
    from health import install_crash_handler, start_heartbeat, alert
    install_crash_handler()
    start_heartbeat(int(os.environ.get("HEARTBEAT_SEC", "0")))
    # startup alert removed — no Slack noise on restart
    _agent = build_agent()
    start_slack(_agent)
    from autoloop import start as start_loop
    start_loop(_agent)
    yield


app = FastAPI(title="Pricing Agent (LangGraph + HF)", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tool_calls: list = []


@app.get("/health")
def health():
    model = os.environ.get("GEMINI_MODEL") or os.environ.get("GROQ_MODEL") or os.environ.get("HF_MODEL") or "unknown"
    from api_client import get_client
    try:
        c = get_client()
        api_ok = c._logged_in
    except Exception:
        api_ok = False
    return {"status": "ok", "model": model, "api_logged_in": api_ok}


@app.post("/autoloop/pause")
def autoloop_pause():
    from autoloop import pause
    pause()
    return {"status": "paused"}

@app.post("/autoloop/resume")
def autoloop_resume():
    from autoloop import resume
    resume()
    return {"status": "resumed"}

@app.get("/autoloop/status")
def autoloop_status():
    from autoloop import is_paused
    import os
    interval = int(os.environ.get("AUTOLOOP_SEC", "0"))
    return {"paused": is_paused(), "interval_sec": interval}


@app.get("/debug/trips")
def debug_trips():
    """Return raw trip data from API — use this to check field names."""
    from api_client import get_client
    from datetime import date
    c = get_client()
    c.search_services("BANGALORE", "TIRUPATI", journey_date=date.today(), refresh=True)
    raw = getattr(c, "_trips", [])
    parsed = c.list_services()
    return {
        "date": date.today().isoformat(),
        "raw_count": len(raw),
        "parsed_count": len(parsed),
        "raw_first": raw[0] if raw else None,   # first raw trip — shows all field names
        "parsed": parsed,                        # what agent sees after mapping
    }


@app.post("/chat/stream", dependencies=[Depends(_require_api_key)])
def chat_stream(req: ChatRequest):
    """SSE stream of agent events: tool_call, tool_result, text chunks, done."""
    if _agent is None:
        raise HTTPException(status_code=503, detail="agent not ready")
    sid = (req.session_id or "").strip() or str(uuid.uuid4())
    config = {"configurable": {"thread_id": sid}, "recursion_limit": int(os.environ.get("AGENT_RECURSION_LIMIT", "60"))}

    def gen():
        import json as _j
        yield {"event": "session", "data": _j.dumps({"session_id": sid})}
        try:
            for chunk in _agent.stream(
                {"messages": [HumanMessage(content=req.message)]},
                config=config,
                stream_mode="updates",
            ):
                for node_name, node_state in chunk.items():
                    msgs = node_state.get("messages", []) if isinstance(node_state, dict) else []
                    for m in msgs:
                        kind = type(m).__name__
                        payload = {"node": node_name, "kind": kind}
                        if hasattr(m, "tool_calls") and m.tool_calls:
                            payload["tool_calls"] = [
                                {"name": c.get("name"), "args": c.get("args")}
                                for c in m.tool_calls
                            ]
                        if m.content:
                            payload["content"] = m.content[:2000]
                        yield {"event": "step", "data": _j.dumps(payload, default=str)}
        except Exception as e:
            yield {"event": "error", "data": _j.dumps({"error": str(e)})}
        yield {"event": "done", "data": "{}"}

    from sse_starlette.sse import EventSourceResponse
    return EventSourceResponse(gen())


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(_require_api_key)])
def chat(req: ChatRequest):
    if _agent is None:
        raise HTTPException(status_code=503, detail="agent not ready")
    sid = (req.session_id or "").strip() or str(uuid.uuid4())
    config = {"configurable": {"thread_id": sid}, "recursion_limit": int(os.environ.get("AGENT_RECURSION_LIMIT", "60"))}
    print(f"\n[agent] ← {req.message[:120]}")
    result = _agent.invoke(
        {"messages": [HumanMessage(content=req.message)]},
        config=config,
    )
    msgs = result["messages"]
    print(f"[agent] {len(msgs)} messages in result")
    for i, m in enumerate(msgs):
        mt = type(m).__name__
        mc = str(m.content or "")[:80]
        tc = getattr(m, "tool_calls", []) or []
        print(f"[agent] msg[{i}] {mt}: content='{mc}' tool_calls={len(tc)}")
    reply = msgs[-1].content if msgs else ""
    # Log every tool the AI called
    for m in msgs:
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                print(f"[agent] tool: {tc.get('name')} {json.dumps(tc.get('args') or {}, ensure_ascii=False)}")
    # Retry up to 2x on empty reply — fresh thread each time
    _max_chat_retries = 2
    for _chat_ri in range(_max_chat_retries):
        if reply.strip():
            break
        print(f"[agent] empty reply attempt {_chat_ri+1}/{_max_chat_retries} — retrying fresh thread")
        _retry_sid = str(uuid.uuid4())
        _retry_result = _agent.invoke(
            {"messages": [HumanMessage(content=req.message)]},
            config={"configurable": {"thread_id": _retry_sid},
                    "recursion_limit": int(os.environ.get("AGENT_RECURSION_LIMIT","150"))},
        )
        msgs = _retry_result.get("messages") or []
        reply = msgs[-1].content if msgs else ""

    # Hallucination guard + auto-retry
    from guard import check as _hcheck
    h = _hcheck(reply, msgs)
    if h["hallucinated"]:
        print(f"[guard] HALLUCINATION: {h['missing']} — retrying")
        retry = _agent.invoke(
            {"messages": [HumanMessage(content=f"You said you did {h['missing']} but never called the tool. CALL the tool now to actually do it.")]},
            config=config,
        )
        msgs = retry["messages"]
        reply = msgs[-1].content if msgs else reply
        h2 = _hcheck(reply, msgs)
        if h2["hallucinated"]:
            reply += f"\n\n⚠️ Still missing tool call for {h2['missing']}. Verify manually."
    tool_calls = []
    print(f"\n=== {len(msgs)} messages ===")
    for m in msgs:
        kind = type(m).__name__
        content_preview = (m.content[:200] if m.content else "")
        print(f"  [{kind}] {content_preview}")
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                tool_calls.append({"name": tc.get("name"), "args": tc.get("args")})
                print(f"    tool_call: {tc.get('name')} {tc.get('args')}")
    # Mirror to Slack channel if configured
    try:
        import os as _os
        from slack_sdk import WebClient
        bot = _os.environ.get("SLACK_BOT_TOKEN", "")
        ch = _os.environ.get("SLACK_CHANNEL", "")
        if bot.startswith("xoxb-") and ch:
            WebClient(token=bot).chat_postMessage(channel=ch, text=f"🤖 {reply}")
    except Exception as e:
        print(f"[slack mirror fail] {e}")
    return ChatResponse(session_id=sid, reply=reply, tool_calls=tool_calls)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")), reload=False)
