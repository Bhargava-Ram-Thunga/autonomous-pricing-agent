"use client";

import type { CSSProperties, ReactNode } from "react";

interface Props {
  title?: string;
  children: ReactNode;
  style?: CSSProperties;
}

export default function Card({ title, children, style }: Props) {
  return (
    <div
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
        padding: "20px 24px",
        ...style,
      }}
    >
      {title && (
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
          {title}
        </h2>
      )}
      {children}
    </div>
  );
}
