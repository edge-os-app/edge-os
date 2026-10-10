import type { Attempt, AttemptStatus, AttemptUsage, Bundle, Finding, ReplyState } from "./types";

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
  attempt_in_flight: "An earlier attempt has no saved result and may still be running, so a retry is not offered.",
  outcome_uncertain: "An earlier attempt may still finish, so a retry is not offered. Nothing was replayed.",
  stale_reply: "Your saved meaning changed after that reply, so the reply cannot be tried again.",
};

export const ATTEMPT_STATUS_LABEL: Record<AttemptStatus, string> = {
  STARTED: "Started, no result saved",
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

/**
 * A first request that has no saved outcome and no revision. The outcome is written in a separate step after the attempt
 * settles, so this state is real: a crash or a storage error can stop between the two. The page words it from the stored
 * attempt, never from the absence of an outcome, and never calls it a verdict on the idea.
 */
export type FirstReadingKind = "UNREAD" | "RUNNING_OR_STOPPED" | "READ_NOT_SAVED" | "FAILED" | "UNCERTAIN";
export interface FirstReading {
  kind: FirstReadingKind;
  title: string;
  lead: string;
  /** Which explicit action fits: start or retry the interpreter, or only look again at the saved record. */
  action: "START" | "RETRY" | "CHECK_AGAIN";
  failure?: FailureKind;
}

export function firstReading(bundle: Pick<Bundle, "attempts" | "interpretations" | "revisions" | "head" | "outcomes">): FirstReading | null {
  const { attempts, head } = bundle;
  if (bundle.interpretations.length > 0 || bundle.revisions.length > 0) return null;
  const last = attempts[attempts.length - 1];
  // The state belongs to the LATEST attempt. An outcome saved for an earlier attempt must not describe a later one.
  if (last && bundle.outcomes.some((o) => o.record.operation_id === last.attempt_id)) return null;
  if (!last && head.outcome !== null) return null; // fixture interpreter: no attempts, its own outcome
  if (!last) {
    return { kind: "UNREAD", title: "Saved, not read yet", action: head.retry.allowed ? "START" : "CHECK_AGAIN",
      lead: "Your request is saved, but the interpreter has not read it yet. Nothing was lost, and nothing was judged." };
  }
  if (last.status === "STARTED") {
    return { kind: "RUNNING_OR_STOPPED", title: "An interpreter attempt has not finished", action: "CHECK_AGAIN",
      lead: "An attempt was started and no result is saved. It may still be running, or it may have stopped. This page cannot tell which. Nothing was judged, and nothing is repeated while it may still run." };
  }
  if (last.status === "COMPLETED" && last.parse_result === "ACCEPTED") {
    return { kind: "READ_NOT_SAVED", title: "Your request was read, and the answer is not saved yet", action: "CHECK_AGAIN",
      lead: "The interpreter answered and the answer was accepted. Saving it did not finish. It is saved when the service restarts. Nothing was judged." };
  }
  if (last.status === "PROVIDER_FAILED") {
    return { kind: "FAILED", failure: "UNAVAILABLE", title: FAILURE_COPY.UNAVAILABLE.title, lead: FAILURE_COPY.UNAVAILABLE.lead,
      action: head.retry.allowed ? "RETRY" : "CHECK_AGAIN" };
  }
  if (last.parse_result?.startsWith("REJECTED:")) {
    return { kind: "FAILED", failure: "MALFORMED_OUTPUT", title: FAILURE_COPY.MALFORMED_OUTPUT.title,
      lead: `${FAILURE_COPY.MALFORMED_OUTPUT.lead} Reason: ${last.parse_result.slice("REJECTED:".length).replaceAll("_", " ")}.`,
      action: head.retry.allowed ? "RETRY" : "CHECK_AGAIN" };
  }
  if (last.status === "TIMED_OUT" || last.status === "UNKNOWN" || last.status === "INTERRUPTED") {
    return { kind: "UNCERTAIN", failure: "OUTCOME_UNKNOWN", title: FAILURE_COPY.OUTCOME_UNKNOWN.title, lead: FAILURE_COPY.OUTCOME_UNKNOWN.lead, action: "CHECK_AGAIN" };
  }
  return null;
}

/** Heading and words for the last reply when it has no saved revision. Each follows from the stored attempt only. */
export function replyCopy(reply: ReplyState): { title: string; body: string } {
  const kept = "Your saved meaning did not change.";
  switch (reply.state) {
    case "REJECTED":
      return reply.reason_code === "reply_changed_nothing"
        ? { title: "Your last reply could not be used", body: "Your reply matched what is already saved, so nothing changed. Say what you want to change, or choose an option." }
        : { title: "Your last reply could not be used", body: `The interpreter's reading broke a rule (${reply.reason_code?.replaceAll("_", " ")}), so none of it was used. ${kept}` };
    case "UNCERTAIN":
      return { title: "We do not know if your last reply was read", body: `The interpreter may or may not have read it. Nothing was retried and ${kept.toLowerCase()}` };
    case "PENDING_SAVE":
      return { title: "Your last reply was read but is not saved yet",
        body: `The interpreter read it and the answer was accepted. Saving it did not finish. It is saved when the service restarts, or the next time this request is answered or retried. ${kept}` };
    case "UNFINISHED":
      return { title: "Your last reply has no saved result",
        body: `An attempt to read your reply was started and no result is saved. It may still be running, or it may have stopped. This page cannot tell which. ${kept} Nothing is repeated while it may still run.` };
    default:
      return { title: "Your last reply was not read", body: `A system failure stopped the interpreter. ${kept}` };
  }
}
