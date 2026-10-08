import type { Expression, FieldEvidence, InputClass, Job, OutcomeName } from "./types";

export const JOB_LABEL: Record<Job, string> = {
  CREATE_STRATEGY: "Create a rule to test",
  INVESTIGATE_EFFECT: "Investigate whether an effect exists",
  COMPARE: "Compare options",
  SIMULATE: "Simulate",
  OBSERVE_FORWARD: "Observe going forward",
  REQUEST_LIVE: "Request live trading",
};

export const CLASS_LABEL: Record<InputClass, string> = {
  LOOSE_INTUITION: "Rough hunch",
  CONCRETE_THESIS: "Specific thesis",
  BOUNDED_NO_THESIS: "No thesis, bounded question",
};

export const SUPPORTED_RESTRICTIONS = ["no leverage", "no additions", "no partial exits", "one open position maximum"];

export const FIELD_LABEL: Record<string, string> = {
  market: "Market", decision_interval_seconds: "Decision interval", data_inputs: "Data inputs", entry: "Entry rule",
  exit: "Exit rule", invalidation: "Invalidation", sizing: "Sizing", additions: "Additions", partial_exits: "Partial exits",
  cost_assumptions: "Cost assumptions", risk_limits: "Risk limits", action_scope: "Action scope", restrictions: "Restrictions",
};

export const ORIGIN_LABEL: Record<FieldEvidence["origin"], string> = {
  USER_STATED: "You said", USER_CONFIRMED: "You chose", AGENT_PROPOSED: "Suggested", APPLICATION_CONFIGURED: "Application default",
};

export const OUTCOME_COPY: Record<OutcomeName, { title: string; tone: "accent" | "accent-2" | "neutral" | "outline" }> = {
  NEEDS_CLARIFICATION: { title: "Needs your answer", tone: "accent" },
  UNSUPPORTED: { title: "Not supported yet", tone: "neutral" },
  UNRESOLVED: { title: "Unresolved: nothing was tested", tone: "neutral" },
  INVALID_INPUT: { title: "Could not be interpreted", tone: "outline" },
  COMPILED: { title: "Ready to review", tone: "accent-2" },
  CONFLICTED: { title: "Conflict", tone: "outline" },
  PUBLISHED: { title: "Saved", tone: "accent-2" },
};

/** Exact: the decimal string shifts two places, with no float rounding. "0.00125" reads "0.125%". */
function percent(value: string): string {
  const negative = value.startsWith("-");
  const [whole = "0", fraction = ""] = value.replace("-", "").split(".");
  const padded = fraction.padEnd(2, "0");
  const digits = (whole + padded.slice(0, 2)).replace(/^0+(?=\d)/, "");
  const rest = padded.slice(2).replace(/0+$/, "");
  return `${negative ? "-" : ""}${digits}${rest ? `.${rest}` : ""}%`;
}

const COMPARE_WORDS: Record<string, string> = { gt: "above", gte: "at or above", lt: "below", lte: "at or below" };

function pctOf(value: string): string { return percent(value.replace("-", "")); }

/** Reads `price_return(n) <op> constant`. Never turns a sign around: the words follow the number. */
function describeReturn(op: string, buckets: number, value: string): string {
  const minutes = buckets * 5;
  const v = Number(value);
  const span = `over the last ${minutes} minutes`;
  if (op === "gt" && v === 0) return `price rose ${span}`;
  if (op === "lt" && v === 0) return `price fell ${span}`;
  if (op === "gt" && v > 0) return `price rose more than ${pctOf(value)} ${span}`;
  if (op === "gte" && v > 0) return `price rose at least ${pctOf(value)} ${span}`;
  if (op === "lt" && v < 0) return `price fell more than ${pctOf(value)} ${span}`;
  if (op === "lte" && v < 0) return `price fell at least ${pctOf(value)} ${span}`;
  return `the ${minutes}-minute price return is ${COMPARE_WORDS[op]} ${v < 0 ? "-" : ""}${pctOf(value)}`;
}

/** Plain-words reading of a supported expression. Falls back to a labelled operator tree. */
export function describeExpression(node: unknown): string {
  const expr = node as Expression;
  if (!expr || typeof expr !== "object" || typeof expr.op !== "string") return "unknown rule";
  const args = (expr.args as Expression[] | undefined) ?? [];
  if (expr.op in COMPARE_WORDS && args.length === 2) {
    const [left, right] = args;
    if (left.op === "price_return" && right.op === "constant") {
      return describeReturn(expr.op, Number(left.lookback_buckets), String(right.value));
    }
    return `${describeExpression(left)} is ${COMPARE_WORDS[expr.op]} ${describeExpression(right)}`;
  }
  switch (expr.op) {
    case "constant": return `${expr.value}`;
    case "price": return "price";
    case "quote_volume": return "quote volume";
    case "price_return": return `price return over ${Number(expr.lookback_buckets) * 5} minutes`;
    case "and": case "or": return args.map(describeExpression).join(` ${expr.op} `);
    case "not": return `not (${describeExpression(expr.value)})`;
    default: return expr.op;
  }
}

function shortAddress(address: unknown): string {
  return typeof address === "string" && address.length > 12 ? `${address.slice(0, 6)}…${address.slice(-4)}` : String(address ?? "unknown");
}

/** Names the market from its value. Only the recorded synthetic fixture is called synthetic. */
function describeMarket(value: unknown): string {
  const v = value as { network?: string; research_binding?: { evidence_class?: string; base_asset?: string; quote_asset?: string }; base_asset?: string; quote_asset?: string };
  if (v?.research_binding?.evidence_class === "SYNTHETIC_FIXTURE") return "Synthetic fixture market (not a real pool)";
  const base = v?.research_binding?.base_asset ?? v?.base_asset, quote = v?.research_binding?.quote_asset ?? v?.quote_asset;
  if (base === "0x1111111111111111111111111111111111111111" && quote === "0x2222222222222222222222222222222222222222")
    return "Synthetic fixture market (not a real pool)";
  return `${v?.network ?? "Unknown network"} market, base ${shortAddress(base)}, quote ${shortAddress(quote)}`;
}

export function summarizeValue(field: string, value: unknown): string {
  if (value === undefined) return "No value yet";
  const v = value as Record<string, unknown>;
  switch (field) {
    case "entry": return `Enter when ${describeExpression(value)}`;
    case "exit": return `Exit when ${describeExpression(value)}`;
    case "invalidation":
      return v && (v as { state?: string }).state === "NOT_REQUESTED" ? "No separate invalidation rule" : `Stop when ${describeExpression(value)}`;
    case "market": return describeMarket(value);
    case "decision_interval_seconds": return `Decide once per ${Number(value) / 60} minutes`;
    case "data_inputs": return (value as string[]).join(", ");
    case "sizing": return `Fixed ${(v as { amount: string }).amount} quote units per entry`;
    case "additions": return value ? "Additions allowed" : "No additions";
    case "partial_exits": return value ? "Partial exits allowed" : "No partial exits";
    case "cost_assumptions": return `${percent((v as { fee_rate: string }).fee_rate)} fee, ${percent((v as { slippage_rate: string }).slippage_rate)} slippage (synthetic assumption)`;
    case "risk_limits": return `At most ${(v as { max_open_positions: number }).max_open_positions} open position, ${(v as { max_quote_notional: string }).max_quote_notional} quote units`;
    case "action_scope": return "Spot buy and sell all attributable inventory. This grants no permission.";
    case "restrictions": return (value as string[]).length ? (value as string[]).join("; ") : "None";
    default: return JSON.stringify(value);
  }
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function shortId(id: string): string { return id.slice(0, 8); }
