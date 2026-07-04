"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Input, TextArea, TextField } from "@heroui/react";

import { AppShell } from "@/components/app-shell";

interface Message {
  id: number;
  role: string;
  content: string;
  created_at: string;
}
interface User {
  email: string;
  name: string;
}

export default function RoomClient({ roomId, user }: { roomId: string; user: User }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [memory, setMemory] = useState("");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [savingMemory, setSavingMemory] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`/api/rooms/${roomId}/chat`)
      .then((r) => r.json())
      .then((d: Message[]) => setMessages(d));
    fetch(`/api/rooms/${roomId}/memory`)
      .then((r) => r.json())
      .then((d: { memory: string }) => setMemory(d.memory ?? ""));
  }, [roomId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    if (!input.trim() || sending) return;
    setSending(true);
    const content = input.trim();
    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "user", content, created_at: new Date().toISOString() },
    ]);
    try {
      const res = await fetch(`/api/rooms/${roomId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const data = (await res.json()) as { reply?: string };
      if (data.reply) {
        setMessages((prev) => [
          ...prev,
          { id: Date.now() + 1, role: "assistant", content: data.reply!, created_at: new Date().toISOString() },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: "Error: could not reach agent",
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function saveMemory() {
    setSavingMemory(true);
    await fetch(`/api/rooms/${roomId}/memory`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ memory }),
    });
    setSavingMemory(false);
  }

  const parts = roomId.split("_");
  const svcNum = parts[0];
  const date = parts.slice(1).join("_");

  return (
    <AppShell user={user} title={`Service ${svcNum}`} headerRight={<span className="text-muted text-xs">{date}</span>}>
      <div className="flex h-full min-h-0">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1 space-y-3 overflow-auto p-4">
            {messages.length === 0 && (
              <p className="text-muted mt-8 text-center text-sm">No messages yet. Start a conversation.</p>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={
                    m.role === "user"
                      ? "bg-accent text-accent-foreground max-w-[75%] rounded-xl px-4 py-2 text-sm"
                      : "bg-surface-secondary text-surface-secondary-foreground max-w-[75%] rounded-xl px-4 py-2 text-sm"
                  }
                >
                  {m.content}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="bg-surface-secondary text-muted rounded-xl px-4 py-2 text-sm">
                  Agent thinking…
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
          <div className="border-border flex gap-2 border-t p-4">
            <TextField value={input} onChange={setInput} className="flex-1">
              <Input
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                placeholder="Type a message…"
              />
            </TextField>
            <Button onPress={sendMessage} isDisabled={sending || !input.trim()}>
              Send
            </Button>
          </div>
        </div>
        <div className="border-border bg-surface flex w-64 shrink-0 flex-col border-l">
          <div className="border-border border-b px-4 py-3">
            <div className="text-sm font-medium">Memory / Instructions</div>
            <div className="text-muted text-xs">Persists across sessions</div>
          </div>
          <TextArea
            value={memory}
            onChange={(e) => setMemory(e.target.value)}
            placeholder="Add instructions or memory for this room…"
            className="flex-1 resize-none border-none bg-transparent p-4"
          />
          <div className="border-border border-t p-3">
            <Button fullWidth variant="secondary" onPress={saveMemory} isDisabled={savingMemory}>
              {savingMemory ? "Saving…" : "Save Memory"}
            </Button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
