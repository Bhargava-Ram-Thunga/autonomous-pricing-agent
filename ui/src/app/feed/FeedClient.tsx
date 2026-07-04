"use client";

import { useEffect, useRef, useState } from "react";
import { Alert, Chip, ScrollShadow } from "@heroui/react";
import { RadioIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";

interface FeedEntry {
  id: number;
  text: string;
  ts: string;
}

export default function FeedClient() {
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let es: EventSource | null = null;
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    function startSSE() {
      try {
        es = new EventSource("/api/agent/chat/stream");
        es.onopen = () => {
          setConnected(true);
          setError(null);
        };
        es.onmessage = (e) => {
          try {
            const data: unknown = JSON.parse(e.data);
            setEntries((prev) => [
              ...prev.slice(-199),
              {
                id: Date.now(),
                text: typeof data === "string" ? data : JSON.stringify(data),
                ts: new Date().toLocaleTimeString(),
              },
            ]);
          } catch {
            setEntries((prev) => [
              ...prev.slice(-199),
              { id: Date.now(), text: e.data, ts: new Date().toLocaleTimeString() },
            ]);
          }
        };
        es.onerror = () => {
          setConnected(false);
          setError("SSE disconnected — falling back to polling");
          es?.close();
          startPolling();
        };
      } catch {
        startPolling();
      }
    }

    function startPolling() {
      pollInterval = setInterval(async () => {
        try {
          const res = await fetch("/api/agent/health");
          if (res.ok) setError("Backend alive (SSE unavailable — polling health)");
        } catch {
          setError("Backend unreachable");
        }
      }, 10000);
    }

    startSSE();
    return () => {
      es?.close();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  return (
    <AppShell
      title="Agent Live Feed"
      headerRight={
        <Chip size="sm" color={connected ? "success" : "default"}>
          <Chip.Label>{connected ? "Live" : "Offline"}</Chip.Label>
        </Chip>
      }
    >
      <div className="flex h-full flex-col">
        {error && (
          <Alert className="m-4 mb-0" status="warning">
            <Alert.Content>
              <Alert.Description>{error}</Alert.Description>
            </Alert.Content>
          </Alert>
        )}
        <ScrollShadow className="flex-1 p-4" orientation="vertical">
          {entries.length === 0 && (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <RadioIcon className="text-muted size-10" />
              <div className="text-sm font-medium">Waiting for agent activity</div>
              <p className="text-muted max-w-xs text-xs">
                Live pricing decisions and alerts will stream here once the agent is running.
              </p>
            </div>
          )}
          <div className="flex flex-col gap-1 font-mono text-sm">
            {entries.map((e) => (
              <div key={e.id} className="flex gap-2">
                <span className="text-muted shrink-0">{e.ts}</span>
                <span>{e.text}</span>
              </div>
            ))}
          </div>
          <div ref={bottomRef} />
        </ScrollShadow>
      </div>
    </AppShell>
  );
}
