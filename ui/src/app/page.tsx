import HealthPanel from "@/components/HealthPanel";
import TripsTable from "@/components/TripsTable";
import ChatPanel from "@/components/ChatPanel";

export const dynamic = "force-dynamic";

const styles = {
  header: {
    padding: "18px 28px",
    borderBottom: "1px solid var(--color-border)",
    display: "flex",
    alignItems: "center",
    gap: 12,
    background: "var(--color-surface)",
  } as const,
  logo: {
    width: 32,
    height: 32,
    borderRadius: 8,
    background: "var(--color-accent)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 900,
    color: "#fff",
    fontSize: 16,
    flexShrink: 0,
  } as const,
  main: {
    padding: "28px",
    maxWidth: 1400,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column" as const,
    gap: 24,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 24,
  } as const,
};

export default function Page() {
  return (
    <>
      <header style={styles.header}>
        <div style={styles.logo}>F</div>
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.2 }}>
            Pricing Agent Dashboard
          </h1>
          <p style={{ fontSize: 12, color: "var(--color-muted)" }}>
            Autonomous pricing agent monitor
          </p>
        </div>
      </header>

      <main style={styles.main}>
        <HealthPanel />
        <TripsTable />
        <div style={styles.grid}>
          <ChatPanel />
          <div
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              padding: "20px 24px",
            }}
          >
            <h2
              style={{
                fontSize: 13,
                fontWeight: 600,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--color-muted)",
                marginBottom: 16,
              }}
            >
              Quick Reference
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                ["GET /health", "Agent + API status"],
                ["GET /autoloop/status", "Loop state & interval"],
                ["POST /autoloop/pause", "Pause autoloop"],
                ["POST /autoloop/resume", "Resume autoloop"],
                ["GET /debug/trips", "Raw + parsed trip data"],
                ["POST /chat", "One-shot agent query"],
                ["POST /chat/stream", "SSE streaming query"],
              ].map(([endpoint, desc]) => (
                <div key={endpoint} style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                  <code
                    style={{
                      fontSize: 11,
                      fontFamily: "monospace",
                      color: "var(--color-accent)",
                      background: "rgba(79,142,247,0.08)",
                      padding: "2px 7px",
                      borderRadius: 4,
                      whiteSpace: "nowrap",
                      flexShrink: 0,
                    }}
                  >
                    {endpoint}
                  </code>
                  <span style={{ fontSize: 12, color: "var(--color-muted)" }}>{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
