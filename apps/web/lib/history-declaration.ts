// The recorded-history declaration must fit the source's real window. The server accepts partitions that are ordered,
// non-overlapping and inside the window, and a schedule on the five-minute grid inside that window. It also requires
// bounded training, validation and holdout partitions for a predictive direction.

export const HISTORY_BUCKET_SECONDS = 300;
export const HISTORY_HORIZON_MINUTES = 5;

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

/**
 * Derive the declaration's partitions and decision schedule from the source window, the largest rule lookback and the
 * five-minute horizon. Every boundary stays on the bucket grid and inside the window.
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

  const maxLookbackBuckets = Math.floor((windowBuckets * BUCKET_MS - HORIZON_MS) / BUCKET_MS);
  if (maxLookbackBuckets < 1) {
    return refusal("The source window is too short for the declared five-minute horizon.");
  }
  const lookback = input.lookbackBuckets;
  if (!Number.isInteger(lookback) || lookback < 1 || lookback > maxLookbackBuckets) {
    const minutes = Math.round((windowBuckets * BUCKET_MS) / 60_000);
    return refusal(`This ${minutes}-minute window supports a lookback of at most ${maxLookbackBuckets} bucket(s) `
      + `with a ${HISTORY_HORIZON_MINUTES}-minute horizon; use a lookback of at most ${maxLookbackBuckets} buckets.`,
    maxLookbackBuckets);
  }

  const partitions = input.direction === "DESCRIPTIVE"
    ? [{ partition_id: "described", role: "DESCRIPTIVE" as const, start: iso(start), end: iso(end) }]
    : predictivePartitions(start, end, windowBuckets);
  if (partitions === null) {
    return refusal("The source window is too short for training, validation and holdout partitions.");
  }

  // A decision needs its lookback buckets behind it and its horizon ahead of it.
  const scheduleStart = start + lookback * BUCKET_MS;
  const scheduleEnd = Math.min(end, end - HORIZON_MS + BUCKET_MS);
  if (scheduleStart >= scheduleEnd) {
    return refusal("The source window is too short for the declared lookback and horizon.", maxLookbackBuckets);
  }
  return {
    ok: true,
    partitions,
    schedule: { version: "p09.decision-clock/1", start: iso(scheduleStart), end: iso(scheduleEnd),
      interval_seconds: HISTORY_BUCKET_SECONDS },
    decisions: (scheduleEnd - scheduleStart) / BUCKET_MS,
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
