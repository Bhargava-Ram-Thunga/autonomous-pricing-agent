"""Custom LangChain chat model wrapping Groq SDK directly.
Solves langchain_groq's tool_calls parsing issues."""
import os
import json
from typing import Any, List, Optional
from groq import Groq
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (AIMessage, BaseMessage, HumanMessage,
                                       SystemMessage, ToolMessage)
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


MAX_MESSAGES = 20  # keep system + last N


def _trim(msgs: List[BaseMessage]) -> List[BaseMessage]:
    """Keep system message + last MAX_MESSAGES-1 messages."""
    if len(msgs) <= MAX_MESSAGES:
        return msgs
    sys_msgs = [m for m in msgs if isinstance(m, SystemMessage)]
    rest = [m for m in msgs if not isinstance(m, SystemMessage)]
    return sys_msgs + rest[-(MAX_MESSAGES - len(sys_msgs)):]


def _safe_args(raw) -> dict:
    """Ensure args is always a plain dict — never None."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}


def _to_groq_messages(msgs: List[BaseMessage]) -> list[dict]:
    msgs = _trim(msgs)
    out = []
    for m in msgs:
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": m.content})
        elif isinstance(m, HumanMessage):
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            d = {"role": "assistant", "content": m.content or ""}
            if m.tool_calls:
                d["tool_calls"] = [
                    {"id": tc.get("id") or f"call_{tc.get('name','fn')}",
                     "type": "function",
                     "function": {"name": tc["name"],
                                  "arguments": json.dumps(_safe_args(tc.get("args")))}}
                    for tc in m.tool_calls
                ]
                d["content"] = m.content or ""
            out.append(d)
        elif isinstance(m, ToolMessage):
            out.append({"role": "tool", "tool_call_id": m.tool_call_id,
                        "content": str(m.content) if m.content is not None else ""})
    return out


class GroqDirectChat(BaseChatModel):
    """Direct Groq SDK chat model with reliable tool_calls parsing."""
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 4096   # 1024 was too low — truncated tool call JSON mid-stream
    tools_schema: Optional[list] = None
    tool_choice: Optional[str] = None
    _groq_client: Any = None  # cached client instance

    @property
    def _llm_type(self) -> str:
        return "groq-direct"

    def _client(self):
        # Cache client to avoid creating a new HTTP connection on every call
        if self._groq_client is None:
            object.__setattr__(self, "_groq_client", Groq(api_key=self.api_key))
        return self._groq_client

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        params = {
            "model": self.model,
            "messages": _to_groq_messages(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.tools_schema:
            params["tools"] = self.tools_schema
            if self.tool_choice:
                params["tool_choice"] = self.tool_choice
        last_err = None
        for attempt in range(4):
            try:
                resp = self._client().chat.completions.create(**params)
                break
            except Exception as e:
                last_err = e
                err = str(e).lower()
                if any(w in err for w in ("429", "rate", "quota", "limit")):
                    wait = 5 * (2 ** attempt)  # 5s, 10s, 20s, 40s
                    print(f"[groq_chat] rate limit (attempt {attempt+1}/4), retry in {wait}s")
                    import time as _t; _t.sleep(wait)
                elif any(w in err for w in ("500", "502", "503", "timeout")):
                    wait = 2 ** attempt
                    import time as _t; _t.sleep(wait)
                else:
                    raise
        else:
            raise last_err
        # Log token usage to Postgres
        try:
            u = resp.usage
            if u:
                from state_store import _get_conn as _pgconn, is_available
                if is_available():
                    with _pgconn().cursor() as _cur:
                        _cur.execute("""
                        INSERT INTO ai.token_usage
                            (model, prompt_tokens, completion_tokens, total_tokens)
                        VALUES (%s, %s, %s, %s)
                        """, (self.model,
                              getattr(u, "prompt_tokens", 0),
                              getattr(u, "completion_tokens", 0),
                              getattr(u, "total_tokens", 0)))
        except Exception:
            pass

        m = resp.choices[0].message
        tool_calls = []
        for c in (m.tool_calls or []):
            try:
                fn = c.function
                if fn is None:
                    continue
                raw_args = fn.arguments
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({
                    "id": c.id or f"call_{fn.name}",
                    "name": fn.name,
                    "args": args if isinstance(args, dict) else {},
                })
            except Exception as e:
                print(f"[groq_chat] tool_call parse error: {e}")
                continue
        ai = AIMessage(content=m.content or "", tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=ai)])

    def bind_tools(self, tools, **kwargs):
        schema = []
        for t in tools:
                # Flatten LangChain Tool to OpenAI tools format
            try:
                from langchain_core.utils.function_calling import convert_to_openai_function
                fn = convert_to_openai_function(t)
            except Exception:
                fn = {"name": t.name, "description": t.description or "",
                      "parameters": {"type": "object", "properties": {}, "required": []}}
            schema.append({"type": "function", "function": fn})
        new = self.__class__(
            model=self.model, api_key=self.api_key,
            temperature=self.temperature, max_tokens=self.max_tokens,
            tools_schema=schema, tool_choice=kwargs.get("tool_choice"),
        )
        return new


_GROQ_PREFERRED_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",  # Llama 4, large context, high quota
    "qwen/qwen3-32b",                             # strong reasoning, large context
    "llama-3.3-70b-versatile",                    # 100K TPD — can exhaust fast
    "llama-3.1-8b-instant",                       # 500K TPD but only 6K TPM limit
]


def _pick_model(preferred: str | None) -> str:
    """Try preferred model; fall back if over quota. Env var overrides all."""
    if preferred:
        return preferred
    env = os.environ.get("GROQ_MODEL", "")
    if env:
        return env
    # Probe each model with a tiny request to find one with quota remaining
    try:
        from groq import Groq as _G
        client = _G(api_key=os.environ["GROQ_API_KEY"])
        available = {m.id for m in client.models.list().data}
        for m in _GROQ_PREFERRED_MODELS:
            if m not in available:
                continue
            try:
                client.chat.completions.create(
                    model=m, messages=[{"role":"user","content":"hi"}], max_tokens=1
                )
                print(f"[groq] auto-selected model: {m}")
                return m
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower() or "rate" in str(e).lower():
                    print(f"[groq] {m} over quota — trying next")
                    continue
                return m  # non-quota error, still use it
    except Exception:
        pass
    return "meta-llama/llama-4-scout-17b-16e-instruct"  # safe fallback, large context


def build(model: Optional[str] = None, **kwargs) -> GroqDirectChat:
    chosen = _pick_model(model)
    print(f"[groq] using model: {chosen}")
    return GroqDirectChat(
        model=chosen,
        api_key=os.environ["GROQ_API_KEY"],
        temperature=0.2,
        max_tokens=4096,
    )
