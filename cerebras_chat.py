"""Custom LangChain chat model wrapping Cerebras SDK directly.
Fast inference, reliable tool calling. Used as primary LLM."""
import os
import json
from typing import Any, List, Optional
from cerebras.cloud.sdk import Cerebras
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (AIMessage, BaseMessage, HumanMessage,
                                      SystemMessage, ToolMessage)
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

MAX_MESSAGES = 20


def _trim(msgs: List[BaseMessage]) -> List[BaseMessage]:
    if len(msgs) <= MAX_MESSAGES:
        return msgs
    sys_msgs = [m for m in msgs if isinstance(m, SystemMessage)]
    rest = [m for m in msgs if not isinstance(m, SystemMessage)]
    return sys_msgs + rest[-(MAX_MESSAGES - len(sys_msgs)):]


def _to_cerebras_messages(msgs: List[BaseMessage]) -> list[dict]:
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
                    {"id": tc.get("id"), "type": "function",
                     "function": {"name": tc["name"],
                                  "arguments": json.dumps(tc.get("args") or {})}}
                    for tc in m.tool_calls
                ]
                d["content"] = m.content or ""
            out.append(d)
        elif isinstance(m, ToolMessage):
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
    return out


class CerebrasDirectChat(BaseChatModel):
    """Direct Cerebras SDK chat model — fast inference + reliable tool calling."""
    model: str = "llama-3.3-70b-instruct"
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 1024
    tools_schema: Optional[list] = None
    tool_choice: Optional[str] = None

    @property
    def _llm_type(self) -> str:
        return "cerebras-direct"

    def _client(self):
        return Cerebras(api_key=self.api_key)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        params = {
            "model": self.model,
            "messages": _to_cerebras_messages(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.tools_schema:
            params["tools"] = self.tools_schema
            if self.tool_choice:
                params["tool_choice"] = self.tool_choice
        resp = self._client().chat.completions.create(**params)
        m = resp.choices[0].message
        ai = AIMessage(
            content=m.content or "",
            tool_calls=[
                {"id": c.id, "name": c.function.name,
                 "args": json.loads(c.function.arguments or "{}")}
                for c in (m.tool_calls or [])
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=ai)])

    def bind_tools(self, tools, **kwargs):
        schema = []
        for t in tools:
            try:
                from langchain_core.utils.function_calling import convert_to_openai_function
                fn = convert_to_openai_function(t)
            except Exception:
                fn = {"name": t.name, "description": t.description or "",
                      "parameters": {"type": "object", "properties": {}, "required": []}}
            schema.append({"type": "function", "function": fn})
        return self.__class__(
            model=self.model, api_key=self.api_key,
            temperature=self.temperature, max_tokens=self.max_tokens,
            tools_schema=schema, tool_choice=kwargs.get("tool_choice"),
        )


def build(model: Optional[str] = None) -> CerebrasDirectChat:
    return CerebrasDirectChat(
        model=model or os.environ.get("CEREBRAS_MODEL", "llama-3.3-70b-instruct"),
        api_key=os.environ["CEREBRAS_API_KEY"],
        temperature=0.2,
        max_tokens=1024,
    )
