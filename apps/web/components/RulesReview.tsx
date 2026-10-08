"use client";

import { Fragment } from "react";
import { describeExpression, summarizeValue } from "../lib/describe";
import type { Strategy } from "../lib/types";

export function RulesReview({ strategy }: { strategy: Strategy }) {
  const rows: [string, string][] = [
    ["Entry", `Enter when ${describeExpression(strategy.entry)}`],
    ["Exit", `Exit when ${describeExpression(strategy.exit)}`],
    ["Invalidation", summarizeValue("invalidation", strategy.invalidation)],
    ["Sizing", summarizeValue("sizing", strategy.sizing)],
    ["Costs", summarizeValue("cost_assumptions", strategy.cost_assumptions)],
    ["Risk limits", summarizeValue("risk_limits", strategy.risk_limits)],
    ["Actions", summarizeValue("action_scope", strategy.action_scope)],
    ["Cadence", `${summarizeValue("decision_interval_seconds", strategy.decision_interval_seconds)}. Needs ${strategy.warmup_buckets} earlier five-minute buckets of history.`],
    ["Trading permission", strategy.execution_permission.state === "NOT_GRANTED" ? "Not granted" : strategy.execution_permission.state],
  ];
  return (
    <dl className="kv" aria-label="Rules in plain words" data-testid="rules-review">
      {rows.map(([k, v]) => (<Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>))}
    </dl>
  );
}
