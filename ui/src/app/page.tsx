import { Card, Chip } from "@heroui/react";
import { TrendingUpIcon } from "lucide-react";

import HealthPanel from "@/components/HealthPanel";
import TripsTable from "@/components/TripsTable";
import ChatPanel from "@/components/ChatPanel";

export const dynamic = "force-dynamic";

const ENDPOINTS: [string, string][] = [
  ["GET /health", "Agent + API status"],
  ["GET /autoloop/status", "Loop state & interval"],
  ["POST /autoloop/pause", "Pause autoloop"],
  ["POST /autoloop/resume", "Resume autoloop"],
  ["GET /debug/trips", "Raw + parsed trip data"],
  ["POST /chat", "One-shot agent query"],
  ["POST /chat/stream", "SSE streaming query"],
];

export default function Page() {
  return (
    <>
      <header className="bg-surface flex items-center gap-3 border-b border-border px-7 py-4">
        <div className="bg-accent text-accent-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
          <TrendingUpIcon className="size-4" />
        </div>
        <div>
          <h1 className="text-sm leading-tight font-semibold">Pricing Agent Dashboard</h1>
          <p className="text-muted text-xs">Autonomous pricing agent monitor</p>
        </div>
      </header>

      <main className="mx-auto flex max-w-[1400px] flex-col gap-6 p-7">
        <HealthPanel />
        <TripsTable />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ChatPanel />
          <Card>
            <Card.Header>
              <Card.Title>Quick Reference</Card.Title>
            </Card.Header>
            <Card.Content className="flex flex-col gap-2.5">
              {ENDPOINTS.map(([endpoint, desc]) => (
                <div key={endpoint} className="flex items-baseline gap-3">
                  <Chip size="sm" variant="soft" className="shrink-0 font-mono">
                    <Chip.Label>{endpoint}</Chip.Label>
                  </Chip>
                  <span className="text-muted text-xs">{desc}</span>
                </div>
              ))}
            </Card.Content>
          </Card>
        </div>
      </main>
    </>
  );
}
