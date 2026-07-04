"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Card, Chip, ScrollShadow, TextArea } from "@heroui/react";
import { SendIcon, WrenchIcon } from "lucide-react";

import { api } from "@/lib/api";

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
        { role: "agent", text: `Error: ${e instanceof Error ? e.message : String(e)}` },
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
    <Card className="flex h-[30rem] flex-col">
      <Card.Header>
        <Card.Title>Chat with Agent</Card.Title>
      </Card.Header>
      <Card.Content className="flex flex-1 flex-col gap-3 overflow-hidden">
        <ScrollShadow className="flex-1" orientation="vertical">
          <div className="flex flex-col gap-3 pr-2">
            {messages.length === 0 && (
              <p className="text-muted text-sm">
                Ask the pricing agent anything — e.g. &ldquo;What is the occupancy on bus 1234
                today?&rdquo;
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
              >
                <div
                  className={
                    m.role === "user"
                      ? "bg-accent text-accent-foreground max-w-[78%] rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap"
                      : "bg-surface-secondary text-surface-secondary-foreground max-w-[78%] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap"
                  }
                >
                  {m.text}
                </div>
                {m.tool_calls && m.tool_calls.length > 0 && (
                  <Chip size="sm" className="mt-1">
                    <WrenchIcon className="size-3" />
                    <Chip.Label>{m.tool_calls.map((t) => t.name).join(", ")}</Chip.Label>
                  </Chip>
                )}
              </div>
            ))}
            {busy && (
              <div className="bg-surface-secondary text-muted w-fit rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm">
                ···
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </ScrollShadow>

        <div className="flex gap-2">
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Message the agent… (Enter to send)"
            rows={2}
            className="flex-1 resize-none"
          />
          <Button onPress={() => void send()} isDisabled={busy || !input.trim()}>
            <SendIcon className="size-4" />
            Send
          </Button>
        </div>
        {sessionId && <div className="text-muted text-xs">session: {sessionId}</div>}
      </Card.Content>
    </Card>
  );
}
