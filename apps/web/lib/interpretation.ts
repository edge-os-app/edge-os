import type { Attempt, AttemptStatus, AttemptUsage, Finding } from "./types";

/** The three ways the interpreter can fail to give a usable answer. None is a verdict on the user's idea. */
export type FailureKind = "MALFORMED_OUTPUT" | "UNAVAILABLE" | "OUTCOME_UNKNOWN";

const FAILURE_BY_CODE: Record<string, FailureKind> = {
  malformed_model_output: "MALFORMED_OUTPUT",
  interpreter_unavailable: "UNAVAILABLE",
  interpreter_outcome_unknown: "OUTCOME_UNKNOWN",
};

export const FAILURE_COPY: Record<FailureKind, { title: string; lead: string }> = {
  MALFORMED_OUTPUT: {
    title: "The interpreter's answer was not usable",
    lead: "The interpreter returned an answer that broke the rules, so none of it was used. This is not a verdict on your idea.",
  },
  UNAVAILABLE: {
    title: "The interpreter did not answer",
    lead: "A system failure stopped the interpreter. This is not a verdict on your idea.",
  },
  OUTCOME_UNKNOWN: {
    title: "We do not know if the interpreter finished",
    lead: "The interpreter may or may not have produced an answer. Nothing was retried and nothing was assumed.",
  },
};

export function systemFailure(findings: Finding[]): FailureKind | null {
  for (const finding of findings) if (finding.code in FAILURE_BY_CODE) return FAILURE_BY_CODE[finding.code];
  return null;
}

export const RETRY_BLOCKED: Record<string, string> = {
  attempt_in_flight: "An attempt is still running. Wait for it to finish.",
  outcome_uncertain: "An earlier attempt may still finish, so a retry is not offered. Nothing was replayed.",
  stale_reply: "Your saved meaning changed after that reply, so the reply cannot be tried again.",
};

export const ATTEMPT_STATUS_LABEL: Record<AttemptStatus, string> = {
  STARTED: "Running",
  COMPLETED: "Finished",
  TRUNCATED: "Cut short",
  PROVIDER_FAILED: "Provider failed",
  TIMED_OUT: "Timed out, outcome unknown",
  INTERRUPTED: "Interrupted, outcome unknown",
  UNKNOWN: "Outcome unknown",
};

export function describeUsage(usage: AttemptUsage): string {
  return usage.source === "PROVIDER_REPORTED"
    ? `${usage.input_tokens?.toLocaleString("en-US")} in, ${usage.output_tokens?.toLocaleString("en-US")} out`
    : "Unknown";
}

export function describeLatency(ms: number | null): string {
  return ms === null ? "Unknown" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function describeParse(parse: string | null): string {
  if (parse === null || parse === "NOT_PARSED") return "No answer to read";
  if (parse === "ACCEPTED") return "Accepted";
  return `Rejected: ${parse.replace(/^REJECTED:/, "").replaceAll("_", " ")}`;
}

export function describePurpose(attempt: Attempt, byId: Map<string, Attempt>): string {
  const base = attempt.purpose === "INTERPRET" ? "First reading" : "Reading your reply";
  const earlier = attempt.retry_of ? byId.get(attempt.retry_of) : undefined;
  return earlier ? `${base}, retry of #${earlier.sequence}` : base;
}

/** The exact words a source reference points at, when they are in the saved request. Replies are kept as hashes only. */
export function sourceQuote(sourceRef: string, original: string): string | null {
  const match = /^intake:original_request#c(\d+)-(\d+)$/.exec(sourceRef);
  if (!match) return null;
  const start = Number(match[1]), end = Number(match[2]);
  return end > start && end <= original.length ? original.slice(start, end) : null;
}
