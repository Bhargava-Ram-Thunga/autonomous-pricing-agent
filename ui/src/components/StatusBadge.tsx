"use client";

interface Props {
  ok: boolean;
  label: string;
}

export default function StatusBadge({ ok, label }: Props) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 10px",
        borderRadius: 20,
        fontSize: 12,
        fontWeight: 600,
        background: ok ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)",
        color: ok ? "var(--color-green)" : "var(--color-red)",
        border: `1px solid ${ok ? "rgba(52,211,153,0.3)" : "rgba(248,113,113,0.3)"}`,
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: ok ? "var(--color-green)" : "var(--color-red)",
        }}
      />
      {label}
    </span>
  );
}
