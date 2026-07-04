/** Thin wrappers around the FastAPI pricing agent endpoints. */

const BASE = "/api/agent";

export interface HealthResponse {
  status: string;
  model: string;
  api_logged_in: boolean;
}

export interface AutoloopStatus {
  paused: boolean;
  interval_sec: number;
}

export interface Trip {
  service_number: string;
  departure: string;
  arrival: string;
  seats_total: number;
  seats_booked: number;
  occupancy_pct: number;
  base_fare: number;
  current_fare: number;
  classification: string;
  pricing_model: string;
}

export interface DebugTripsResponse {
  date: string;
  raw_count: number;
  parsed_count: number;
  raw_first: unknown;
  parsed: Trip[];
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  tool_calls: { name: string; args: Record<string, unknown> }[];
}

async function get<T>(path: string): Promise<T> {
  const headers: Record<string, string> = {};
  const key = process.env.NEXT_PUBLIC_AGENT_API_KEY;
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(`${BASE}${path}`, { headers, cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const key = process.env.NEXT_PUBLIC_AGENT_API_KEY;
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<HealthResponse>("/health"),
  autoloopStatus: () => get<AutoloopStatus>("/autoloop/status"),
  autoloopPause: () => post<{ status: string }>("/autoloop/pause"),
  autoloopResume: () => post<{ status: string }>("/autoloop/resume"),
  debugTrips: () => get<DebugTripsResponse>("/debug/trips"),
  chat: (req: ChatRequest) => post<ChatResponse>("/chat", req),
};
