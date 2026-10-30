"use client";

import type { ReactNode } from "react";

/** One collapsed proof-data control. Native details/summary, so it works without JavaScript. */
export function Details({ summary = "Details", children, testId, open }: {
  summary?: string;
  children: ReactNode;
  testId?: string;
  open?: boolean;
}) {
  return (
    <details data-testid={testId} open={open}>
      <summary style={{ minHeight: 44, cursor: "pointer" }}>{summary}</summary>
      {children}
    </details>
  );
}
