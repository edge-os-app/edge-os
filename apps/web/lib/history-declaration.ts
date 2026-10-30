// The recorded-history declaration must fit the source's real window AND the partition the server can read.
// The server accepts partitions that are ordered, non-overlapping and inside the window, and a schedule on the
// five-minute grid inside that window. It requires bounded training, validation and holdout partitions for a
// predictive direction. At comparison time it reads only TRAINING or DESCRIPTIVE partitions, so the schedule must
// leave every decision's lookback and horizon inside that readable partition.

export const HISTORY_BUCKET_SECONDS = 300;
export const HISTORY_HORIZON_MINUTES = 5;
/** The floors an accepted declaration must be able to meet: one triggered and one control decision. */
export const HISTORY_DECISION_FLOOR = 2;

export type HistoryDirection = "DESCRIPTIVE" | "OUTPERFORM" | "UNDERPERFORM";
export type HistoryPartition = {
  partition_id: string; role: "DESCRIPTIVE" | "TRAINING" | "VALIDATION" | "HOLDOUT"; start: string; end: string;
};
export type HistorySchedule = {
  version: "p09.decision-clock/1"; start: string; end: string; interval_seconds: number;
};
export type HistoryPlan =
  | { ok: true; partitions: HistoryPartition[]; schedule: HistorySchedule; decisions: number }
  | { ok: false; reason: string; maxLookbackBuckets: number | null };

const BUCKET_MS = HISTORY_BUCKET_SECONDS * 1000;
const HORIZON_MS = HISTORY_HORIZON_MINUTES * 60 * 1000;
/** The comparison reads the first trade in a one-minute window at each reference time (P09 reference_trade). */
const RESPONSE_WINDOW_MS = 60 * 1000;

function iso(value: number): string {
  return new Date(value).toISOString().replace(".000Z", "Z");
}

function refusal(reason: string, maxLookbackBuckets: number | null = null): HistoryPlan {
  return { ok: false, reason, maxLookbackBuckets };
}

/** Split the window into the three bounded partitions the server requires, in buckets, keeping the old proportions. */
function predictivePartitions(start: number, end: number, windowBuckets: number): HistoryPartition[] | null {
  const validate = Math.max(1, Math.floor(windowBuckets / 4));
  const holdout = Math.max(1, Math.floor(windowBuckets / 4));
  const train = windowBuckets - validate - holdout;
  if (train < 1) return null;
  const trainEnd = start + train * BUCKET_MS;
  const validateEnd = trainEnd + validate * BUCKET_MS;
  return [
    { partition_id: "train", role: "TRAINING", start: iso(start), end: iso(trainEnd) },
    { partition_id: "validate", role: "VALIDATION", start: iso(trainEnd), end: iso(validateEnd) },
    { partition_id: "holdout", role: "HOLDOUT", start: iso(validateEnd), end: iso(end) },
  ];
}

function directionLabel(direction: HistoryDirection): string {
  return direction === "DESCRIPTIVE" ? "DESCRIPTIVE" : direction;
}

/**
 * Derive the declaration's partitions and decision schedule from the source window, the largest rule lookback and the
 * five-minute horizon. The schedule lives in the readable partition: TRAINING for predictive work, the whole window
 * for DESCRIPTIVE work. Every decision keeps its lookback behind it and its horizon ahead of it in that partition.
 */
export function deriveHistoryPlan(input: {
  window: { start: string; end: string };
  direction: HistoryDirection;
  lookbackBuckets: number;
}): HistoryPlan {
  const start = Date.parse(input.window.start);
  const end = Date.parse(input.window.end);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
    return refusal("The source window has no usable start and end.");
  }
  if (start % BUCKET_MS || end % BUCKET_MS) {
    return refusal("The source window is not on the five-minute bucket grid.");
  }
  const windowBuckets = (end - start) / BUCKET_MS;
  if (!Number.isInteger(windowBuckets)) return refusal("The source window is not a whole number of buckets.");

  const partitions = input.direction === "DESCRIPTIVE"
    ? [{ partition_id: "described", role: "DESCRIPTIVE" as const, start: iso(start), end: iso(end) }]
    : predictivePartitions(start, end, windowBuckets);
  if (partitions === null) {
    return refusal("The source window is too short for training, validation and holdout partitions.");
  }

  // The server reads only this partition at comparison time. Its buckets start one bucket after its start.
  const readableStart = Date.parse(partitions[0].start);
  const readableEnd = Date.parse(partitions[0].end);
  // The last decision must leave the horizon and the one-minute reference window inside the readable partition.
  const lastGrid = Math.floor((readableEnd - HORIZON_MS - RESPONSE_WINDOW_MS - readableStart) / BUCKET_MS);
  const lastDecision = lastGrid < 0 ? readableStart - BUCKET_MS : readableStart + lastGrid * BUCKET_MS;
  // A decision at t uses the feature bucket ending at t - lookback buckets, so the first decision is lookback + 1
  // buckets after the partition start. Predictive work must fit the 1 triggered + 1 control floor; descriptive work
  // keeps its outcome claim, so one usable decision is accepted (COMMON1 item 3).
  const required = input.direction === "DESCRIPTIVE" ? 1 : HISTORY_DECISION_FLOOR;
  const maxLookbackBuckets = lastGrid - required;
  const lookback = input.lookbackBuckets;
  const minutes = Math.round((windowBuckets * BUCKET_MS) / 60_000);
  if (maxLookbackBuckets < 1) {
    if (input.direction === "DESCRIPTIVE") {
      return refusal(`This ${minutes}-minute window has no usable decision in its readable partition with a `
        + `${HISTORY_HORIZON_MINUTES}-minute horizon and its 60-second response window.`);
    }
    return refusal(`This ${minutes}-minute window supports at most ${Math.max(0, lastGrid)} usable decision(s) `
      + `in its training partition for ${directionLabel(input.direction)}. Predictive work needs at least `
      + `${HISTORY_DECISION_FLOOR} decisions (1 triggered and 1 control). No lookback fits; use DESCRIPTIVE.`);
  }
  if (!Number.isInteger(lookback) || lookback < 1 || lookback > maxLookbackBuckets) {
    const floorText = input.direction === "DESCRIPTIVE" ? "one usable decision" : "two usable decisions";
    return refusal(`This ${minutes}-minute window supports at most ${maxLookbackBuckets} bucket(s) of lookback for `
      + `${directionLabel(input.direction)} at a ${HISTORY_HORIZON_MINUTES}-minute horizon (${floorText}); `
      + `use a lookback of at most ${maxLookbackBuckets} buckets.`, maxLookbackBuckets);
  }

  const scheduleStart = readableStart + (lookback + 1) * BUCKET_MS;
  const scheduleEnd = lastDecision + BUCKET_MS;
  const decisions = (lastDecision - scheduleStart) / BUCKET_MS + 1;
  if (decisions < required) {
    return refusal(`This ${minutes}-minute window supports only ${decisions} usable decision(s) in its readable `
      + `partition for ${directionLabel(input.direction)}; use a lookback of at most ${maxLookbackBuckets - 1} buckets.`,
    maxLookbackBuckets - 1);
  }
  return {
    ok: true,
    partitions,
    schedule: { version: "p09.decision-clock/1", start: iso(scheduleStart), end: iso(scheduleEnd),
      interval_seconds: HISTORY_BUCKET_SECONDS },
    decisions,
  };
}

/** The limits text the declaration declares. A synthetic recording measures no real pool; an actual source names it. */
export function historyUnknowns(evidenceClass: string, releaseId: string | null): string[] {
  if (evidenceClass === "PROVIDER_ACTUAL") {
    return [`Recorded responses come from the named providers under the approved release`
      + `${releaseId ? ` ${releaseId}` : ""}. Costs are not modelled; the window is short.`];
  }
  return ["Recorded responses are synthetic; no real pool behaviour is measured."];
}
