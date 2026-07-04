"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import Card from "./Card";

interface Message {
  role: "user" | "agent";
  text: string;
  tool_calls?: { name: string; args: Record<string, unknown> }[];
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await api.chat({ message: text, session_id: sessionId });
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "agent", text: res.reply, tool_calls: res.tool_calls },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "agent", text: `⚠ Error: ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setBusy(false);
    }
  }, [input, busy, sessionId]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <Card title="Chat with Agent" style={{ display: "flex", flexDirection: "column", height: 480 }}>
      {/* messages */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 12,
          paddingRight: 4,
          marginBottom: 16,
        }}
      >
        {messages.length === 0 && (
          <p style={{ color: "var(--color-muted)", fontSize: 13, marginTop: 8 }}>
            Ask the pricing agent anything — e.g. "What is the occupancy on bus 1234 today?"
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: m.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                maxWidth: "78%",
                padding: "10px 14px",
                borderRadius: m.role === "user" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                background:
                  m.role === "user"
                    ? "rgba(79,142,247,0.18)"
                    : "rgba(255,255,255,0.05)",
                border: `1px solid ${m.role === "user" ? "rgba(79,142,247,0.3)" : "var(--color-border)"}`,
                fontSize: 13,
                lineHeight: 1.55,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {m.text}
            </div>
            {m.tool_calls && m.tool_calls.length > 0 && (
              <div
                style={{
                  marginTop: 4,
                  fontSize: 11,
                  color: "var(--color-muted)",
                  maxWidth: "78%",
                }}
              >
                🔧 tools: {m.tool_calls.map((t) => t.name).join(", ")}
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div style={{ display: "flex", alignItems: "flex-start" }}>
            <div
              style={{
                padding: "10px 14px",
                borderRadius: "14px 14px 14px 4px",
                background: "rgba(255,255,255,0.05)",
                border: "1px solid var(--color-border)",
                color: "var(--color-muted)",
                fontSize: 13,
              }}
            >
              ···
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* input */}
      <div style={{ display: "flex", gap: 8 }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Message the agent… (Enter to send)"
          rows={2}
          style={{
            flex: 1,
            background: "var(--color-bg)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            padding: "8px 12px",
            color: "var(--color-text)",
            fontSize: 13,
            resize: "none",
            outline: "none",
            fontFamily: "inherit",
            lineHeight: 1.5,
          }}
        />
        <button
          onClick={() => void send()}
          disabled={busy || !input.trim()}
          style={{
            padding: "0 18px",
            borderRadius: 8,
            border: "none",
            background: busy || !input.trim() ? "var(--color-border)" : "var(--color-accent)",
            color: busy || !input.trim() ? "var(--color-muted)" : "#fff",
            fontWeight: 700,
            fontSize: 13,
            transition: "background 0.2s",
          }}
        >
          Send
        </button>
      </div>
      {sessionId && (
        <div style={{ marginTop: 6, fontSize: 11, color: "var(--color-muted)" }}>
          session: {sessionId}
        </div>
      )}
    </Card>
  );
}
