"use client";

import { useState, useCallback } from "react";
import { api, type DebugTripsResponse, type Trip } from "@/lib/api";
import Card from "./Card";

function OccupancyBar({ pct }: { pct: number }) {
  const color =
    pct >= 80 ? "var(--color-red)" : pct >= 50 ? "var(--color-yellow)" : "var(--color-green)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: 6,
          background: "var(--color-border)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${Math.min(100, pct)}%`,
            height: "100%",
            background: color,
            transition: "width 0.4s",
          }}
        />
      </div>
      <span style={{ fontSize: 12, color, minWidth: 36, textAlign: "right" }}>
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}

function ClassBadge({ cls }: { cls: string }) {
  const colors: Record<string, string> = {
    Super_High: "#f87171",
    Special_High: "#fb923c",
    Ultra_High: "#f97316",
    High: "#fbbf24",
    Medium: "#a78bfa",
    Low: "#60a5fa",
    Super_Low: "#94a3b8",
    Festive: "#f472b6",
  };
  const bg = colors[cls] ?? "var(--color-muted)";
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 700,
        padding: "2px 8px",
        borderRadius: 4,
        background: `${bg}22`,
        color: bg,
        border: `1px solid ${bg}44`,
        whiteSpace: "nowrap",
      }}
    >
      {cls.replace(/_/g, " ")}
    </span>
  );
}

const TH: React.CSSProperties = {
  padding: "8px 12px",
  textAlign: "left",
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: "0.05em",
  textTransform: "uppercase",
  color: "var(--color-muted)",
  borderBottom: "1px solid var(--color-border)",
  whiteSpace: "nowrap",
};

const TD: React.CSSProperties = {
  padding: "10px 12px",
  borderBottom: "1px solid var(--color-border)",
  fontSize: 13,
};

export default function TripsTable() {
  const [data, setData] = useState<DebugTripsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.debugTrips();
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <Card
      title={
        data
          ? `Live Trips — ${data.date} (${data.parsed_count} services)`
          : "Live Trips"
      }
    >
      <div style={{ marginBottom: 12 }}>
        <button
          onClick={() => void load()}
          disabled={loading}
          style={{
            padding: "7px 18px",
            borderRadius: 6,
            border: "1px solid var(--color-accent)",
            background: "rgba(79,142,247,0.12)",
            color: "var(--color-accent)",
            fontWeight: 600,
            fontSize: 13,
            opacity: loading ? 0.5 : 1,
          }}
        >
          {loading ? "Fetching…" : data ? "↺ Refresh" : "Load Trips"}
        </button>
        {error && (
          <span style={{ marginLeft: 12, color: "var(--color-red)", fontSize: 13 }}>
            ⚠ {error}
          </span>
        )}
      </div>

      {data && data.parsed.length === 0 && (
        <p style={{ color: "var(--color-muted)", fontSize: 13 }}>No trips found.</p>
      )}

      {data && data.parsed.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={TH}>Service</th>
                <th style={TH}>Departure</th>
                <th style={TH}>Arrival</th>
                <th style={{ ...TH, minWidth: 140 }}>Occupancy</th>
                <th style={TH}>Base ₹</th>
                <th style={TH}>Current ₹</th>
                <th style={TH}>Classification</th>
                <th style={TH}>Model</th>
              </tr>
            </thead>
            <tbody>
              {data.parsed.map((t: Trip) => (
                <tr
                  key={t.service_number}
                  style={{ transition: "background 0.15s" }}
                  onMouseEnter={(e) =>
                    ((e.currentTarget as HTMLTableRowElement).style.background =
                      "rgba(255,255,255,0.03)")
                  }
                  onMouseLeave={(e) =>
                    ((e.currentTarget as HTMLTableRowElement).style.background = "transparent")
                  }
                >
                  <td style={{ ...TD, fontWeight: 600, fontFamily: "monospace" }}>
                    {t.service_number}
                  </td>
                  <td style={TD}>{t.departure}</td>
                  <td style={TD}>{t.arrival}</td>
                  <td style={TD}>
                    <OccupancyBar pct={t.occupancy_pct ?? 0} />
                    <div style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 2 }}>
                      {t.seats_booked ?? "?"}/{t.seats_total ?? "?"} seats
                    </div>
                  </td>
                  <td style={{ ...TD, fontFamily: "monospace" }}>
                    {t.base_fare != null ? `₹${t.base_fare}` : "—"}
                  </td>
                  <td style={{ ...TD, fontFamily: "monospace", fontWeight: 600 }}>
                    {t.current_fare != null ? `₹${t.current_fare}` : "—"}
                  </td>
                  <td style={TD}>
                    <ClassBadge cls={t.classification ?? "—"} />
                  </td>
                  <td style={{ ...TD, color: "var(--color-muted)", fontSize: 12 }}>
                    {(t.pricing_model ?? "—").replace(/_/g, " ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
