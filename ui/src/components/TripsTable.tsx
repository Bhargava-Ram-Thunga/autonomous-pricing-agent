"use client";

import { useCallback, useState } from "react";
import { Alert, Button, Card, Chip, ProgressBar } from "@heroui/react";
import { RefreshCwIcon } from "lucide-react";

import { api, type DebugTripsResponse, type Trip } from "@/lib/api";

const CLASS_COLOR: Record<string, "danger" | "warning" | "default" | "accent"> = {
  Super_High: "danger",
  Special_High: "danger",
  Ultra_High: "danger",
  High: "warning",
  Medium: "warning",
  Low: "default",
  Super_Low: "default",
  Festive: "accent",
};

function OccupancyCell({ trip }: { trip: Trip }) {
  const pct = trip.occupancy_pct ?? 0;
  return (
    <div className="flex min-w-[9rem] flex-col gap-1">
      <div className="flex items-center gap-2">
        <ProgressBar
          value={Math.min(100, pct)}
          color={pct >= 80 ? "danger" : pct >= 50 ? "warning" : "success"}
          className="flex-1"
        />
        <span className="text-muted w-10 shrink-0 text-right text-xs">{pct.toFixed(0)}%</span>
      </div>
      <div className="text-muted text-xs">
        {trip.seats_booked ?? "?"}/{trip.seats_total ?? "?"} seats
      </div>
    </div>
  );
}

const TH = "px-3 py-2 text-left text-xs font-semibold tracking-wide text-muted uppercase border-b border-border whitespace-nowrap";
const TD = "px-3 py-2.5 border-b border-border text-sm";

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
    <Card>
      <Card.Header className="flex-row items-center justify-between">
        <Card.Title>
          {data ? `Live Trips — ${data.date} (${data.parsed_count} services)` : "Live Trips"}
        </Card.Title>
        <Button size="sm" variant="outline" onPress={() => void load()} isDisabled={loading}>
          <RefreshCwIcon className={loading ? "size-4 animate-spin" : "size-4"} />
          {data ? "Refresh" : "Load Trips"}
        </Button>
      </Card.Header>
      <Card.Content>
        {error && (
          <Alert status="danger" className="mb-4">
            <Alert.Content>
              <Alert.Description>{error}</Alert.Description>
            </Alert.Content>
          </Alert>
        )}

        {data && data.parsed.length === 0 && (
          <p className="text-muted py-6 text-center text-sm">No trips found.</p>
        )}

        {data && data.parsed.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className={TH}>Service</th>
                  <th className={TH}>Departure</th>
                  <th className={TH}>Arrival</th>
                  <th className={`${TH} min-w-36`}>Occupancy</th>
                  <th className={TH}>Base ₹</th>
                  <th className={TH}>Current ₹</th>
                  <th className={TH}>Classification</th>
                  <th className={TH}>Model</th>
                </tr>
              </thead>
              <tbody>
                {data.parsed.map((t: Trip) => (
                  <tr key={t.service_number} className="hover:bg-surface-secondary/60">
                    <td className={`${TD} font-mono font-semibold`}>{t.service_number}</td>
                    <td className={TD}>{t.departure}</td>
                    <td className={TD}>{t.arrival}</td>
                    <td className={TD}>
                      <OccupancyCell trip={t} />
                    </td>
                    <td className={`${TD} font-mono`}>
                      {t.base_fare != null ? `₹${t.base_fare}` : "—"}
                    </td>
                    <td className={`${TD} font-mono font-semibold`}>
                      {t.current_fare != null ? `₹${t.current_fare}` : "—"}
                    </td>
                    <td className={TD}>
                      <Chip size="sm" color={CLASS_COLOR[t.classification ?? ""] ?? "default"}>
                        <Chip.Label>{(t.classification ?? "—").replace(/_/g, " ")}</Chip.Label>
                      </Chip>
                    </td>
                    <td className={`${TD} text-muted text-xs`}>
                      {(t.pricing_model ?? "—").replace(/_/g, " ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card.Content>
    </Card>
  );
}
