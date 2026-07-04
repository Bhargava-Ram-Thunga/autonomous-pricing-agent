"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Chip, Spinner } from "@heroui/react";
import { PauseIcon, PlayIcon, RefreshCwIcon } from "lucide-react";

import { api, type AutoloopStatus, type HealthResponse } from "@/lib/api";

export default function HealthPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loop, setLoop] = useState<AutoloopStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, l] = await Promise.all([api.health(), api.autoloopStatus()]);
      setHealth(h);
      setLoop(l);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 15_000);
    return () => clearInterval(id);
  }, [refresh]);

  const toggleLoop = async () => {
    if (!loop) return;
    setToggling(true);
    try {
      if (loop.paused) {
        await api.autoloopResume();
      } else {
        await api.autoloopPause();
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setToggling(false);
    }
  };

  return (
    <Card>
      <Card.Header>
        <Card.Title>Agent Status</Card.Title>
      </Card.Header>
      <Card.Content>
        {error && (
          <Alert status="danger" className="mb-4">
            <Alert.Content>
              <Alert.Description>{error}</Alert.Description>
            </Alert.Content>
          </Alert>
        )}
        <div className="flex flex-wrap items-center gap-5">
          <div className="flex flex-wrap items-center gap-2">
            {health ? (
              <>
                <Chip color={health.status === "ok" ? "success" : "danger"}>
                  <Chip.Label>API</Chip.Label>
                </Chip>
                <Chip color={health.api_logged_in ? "success" : "danger"}>
                  <Chip.Label>Portal Login</Chip.Label>
                </Chip>
                <span className="text-muted text-xs">
                  Model: <strong className="text-foreground">{health.model}</strong>
                </span>
              </>
            ) : (
              <span className="text-muted text-sm">{loading ? "Loading…" : "Unavailable"}</span>
            )}
          </div>

          {loop && (
            <div className="ml-auto flex items-center gap-2">
              <Chip color={loop.paused ? "default" : "success"}>
                <Chip.Label>{loop.paused ? "Autoloop paused" : "Autoloop running"}</Chip.Label>
              </Chip>
              {loop.interval_sec > 0 && (
                <span className="text-muted text-xs">every {loop.interval_sec}s</span>
              )}
              <Button size="sm" variant="outline" onPress={() => void toggleLoop()} isDisabled={toggling}>
                {toggling ? <Spinner size="sm" /> : loop.paused ? <PlayIcon className="size-4" /> : <PauseIcon className="size-4" />}
                {loop.paused ? "Resume" : "Pause"}
              </Button>
            </div>
          )}

          <Button size="sm" variant="ghost" onPress={() => void refresh()} isDisabled={loading}>
            <RefreshCwIcon className={loading ? "size-4 animate-spin" : "size-4"} />
            Refresh
          </Button>
        </div>
      </Card.Content>
    </Card>
  );
}
