"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type HealthResponse, type AutoloopStatus } from "@/lib/api";
import Card from "./Card";
import StatusBadge from "./StatusBadge";

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
    <Card title="Agent Status">
      {error && (
        <p style={{ color: "var(--color-red)", marginBottom: 12, fontSize: 13 }}>
          ⚠ {error}
        </p>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 20, alignItems: "center" }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {health ? (
            <>
              <StatusBadge ok={health.status === "ok"} label="API" />
              <StatusBadge ok={health.api_logged_in} label="Portal Login" />
              <span
                style={{
                  fontSize: 12,
                  color: "var(--color-muted)",
                  alignSelf: "center",
                }}
              >
                Model: <strong style={{ color: "var(--color-text)" }}>{health.model}</strong>
              </span>
            </>
          ) : (
            <span style={{ color: "var(--color-muted)", fontSize: 13 }}>
              {loading ? "Loading…" : "Unavailable"}
            </span>
          )}
        </div>

        {loop && (
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginLeft: "auto" }}>
            <StatusBadge ok={!loop.paused} label={loop.paused ? "Autoloop paused" : "Autoloop running"} />
            {loop.interval_sec > 0 && (
              <span style={{ fontSize: 12, color: "var(--color-muted)" }}>
                every {loop.interval_sec}s
              </span>
            )}
            <button
              onClick={() => void toggleLoop()}
              disabled={toggling}
              style={{
                padding: "5px 14px",
                borderRadius: 6,
                border: "1px solid var(--color-border)",
                background: loop.paused ? "rgba(52,211,153,0.15)" : "rgba(248,113,113,0.15)",
                color: loop.paused ? "var(--color-green)" : "var(--color-red)",
                fontWeight: 600,
                fontSize: 12,
                opacity: toggling ? 0.5 : 1,
              }}
            >
              {toggling ? "…" : loop.paused ? "Resume" : "Pause"}
            </button>
          </div>
        )}

        <button
          onClick={() => void refresh()}
          disabled={loading}
          style={{
            padding: "5px 14px",
            borderRadius: 6,
            border: "1px solid var(--color-border)",
            background: "transparent",
            color: "var(--color-muted)",
            fontSize: 12,
            opacity: loading ? 0.5 : 1,
          }}
        >
          {loading ? "…" : "↺ Refresh"}
        </button>
      </div>
    </Card>
  );
}
