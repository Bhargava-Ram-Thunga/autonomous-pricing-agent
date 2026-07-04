"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Card, Chip, Separator, Skeleton, Spinner } from "@heroui/react";
import { PauseIcon, PlayIcon, WorkflowIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";

interface AutoloopStatus {
  running: boolean;
  paused?: boolean;
  last_run?: string;
  next_run?: string;
}

export default function AutoloopClient() {
  const [status, setStatus] = useState<AutoloopStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchStatus() {
    try {
      const res = await fetch("/api/agent/autoloop/status");
      if (res.ok) setStatus((await res.json()) as AutoloopStatus);
      else setError("Could not fetch status");
    } catch {
      setError("Backend unreachable");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 15000);
    return () => clearInterval(t);
  }, []);

  async function action(endpoint: string) {
    setActing(true);
    try {
      const res = await fetch(`/api/agent/${endpoint}`, { method: "POST" });
      if (!res.ok) throw new Error("Action failed");
      await fetchStatus();
    } catch {
      setError("Action failed");
    } finally {
      setActing(false);
    }
  }

  const isPaused = !status?.running || status?.paused === true;

  return (
    <AppShell title="Autoloop Control">
      <div className="p-6">
        {error && (
          <Alert status="danger" className="mb-4 max-w-sm">
            <Alert.Content>
              <Alert.Description>{error}</Alert.Description>
            </Alert.Content>
          </Alert>
        )}

        {loading && <Skeleton className="h-48 w-full max-w-sm rounded-xl" />}

        {status && (
          <Card className="max-w-sm">
            <Card.Header className="flex-row items-center gap-2">
              <Chip color={isPaused ? "default" : "success"}>
                <Chip.Label>{isPaused ? "Paused" : "Running"}</Chip.Label>
              </Chip>
              <Card.Title className="text-sm font-medium">Autonomous pricing loop</Card.Title>
            </Card.Header>
            <Card.Content className="flex flex-col gap-3">
              <div className="text-muted flex flex-col gap-1 text-xs">
                {status.last_run && <div>Last run: {status.last_run}</div>}
                {status.next_run && <div>Next run: {status.next_run}</div>}
              </div>
              <Separator />
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  variant="secondary"
                  onPress={() => action("autoloop/pause")}
                  isDisabled={acting || isPaused}
                >
                  {acting ? <Spinner size="sm" /> : <PauseIcon className="size-4" />}
                  Pause
                </Button>
                <Button
                  className="flex-1"
                  onPress={() => action("autoloop/resume")}
                  isDisabled={acting || !isPaused}
                >
                  {acting ? <Spinner size="sm" /> : <PlayIcon className="size-4" />}
                  Resume
                </Button>
              </div>
            </Card.Content>
          </Card>
        )}

        {!loading && !status && !error && (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <WorkflowIcon className="text-muted size-10" />
            <div className="text-sm font-medium">Backend offline</div>
            <p className="text-muted max-w-xs text-xs">
              Start the FastAPI backend to control the autoloop.
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
