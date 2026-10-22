import { describe, expect, it } from "vitest";
import { deriveHistoryPlan, historyUnknowns } from "../lib/history-declaration";

// The live MOE source: a twenty-minute window on the five-minute bucket grid.
const MOE = { start: "2026-10-22T07:35:00Z", end: "2026-10-22T07:55:00Z" };
// The synthetic recorded source: two hours, the window the old code assumed.
const SYNTHETIC = { start: "2026-09-25T10:00:00Z", end: "2026-09-25T12:00:00Z" };

function plan(window: { start: string; end: string }, lookbackBuckets: number,
              direction: "DESCRIPTIVE" | "OUTPERFORM" | "UNDERPERFORM" = "OUTPERFORM") {
  const result = deriveHistoryPlan({ window, direction, lookbackBuckets });
  if (!result.ok) throw new Error(`expected a plan, got refusal: ${result.reason}`);
  return result;
}

describe("deriveHistoryPlan", () => {
  it("keeps the synthetic two-hour split exactly as before", () => {
    const result = plan(SYNTHETIC, 2);
    expect(result.partitions).toEqual([
      { partition_id: "train", role: "TRAINING", start: "2026-09-25T10:00:00Z", end: "2026-09-25T11:00:00Z" },
      { partition_id: "validate", role: "VALIDATION", start: "2026-09-25T11:00:00Z", end: "2026-09-25T11:30:00Z" },
      { partition_id: "holdout", role: "HOLDOUT", start: "2026-09-25T11:30:00Z", end: "2026-09-25T12:00:00Z" },
    ]);
  });

  it("splits the twenty-minute MOE window on bucket boundaries for lookback 1", () => {
    const result = plan(MOE, 1);
    expect(result.partitions).toEqual([
      { partition_id: "train", role: "TRAINING", start: "2026-10-22T07:35:00Z", end: "2026-10-22T07:45:00Z" },
      { partition_id: "validate", role: "VALIDATION", start: "2026-10-22T07:45:00Z", end: "2026-10-22T07:50:00Z" },
      { partition_id: "holdout", role: "HOLDOUT", start: "2026-10-22T07:50:00Z", end: "2026-10-22T07:55:00Z" },
    ]);
    expect(result.schedule).toEqual({ version: "p09.decision-clock/1", start: "2026-10-22T07:40:00Z",
      end: "2026-10-22T07:55:00Z", interval_seconds: 300 });
    expect(result.decisions).toBe(3);
  });

  it("still fits lookback 3 in the MOE window with one decision", () => {
    const result = plan(MOE, 3);
    expect(result.schedule.start).toBe("2026-10-22T07:50:00Z");
    expect(result.schedule.end).toBe("2026-10-22T07:55:00Z");
    expect(result.decisions).toBe(1);
  });

  it("refuses lookback 4 with the lookback that fits", () => {
    const result = deriveHistoryPlan({ window: MOE, direction: "OUTPERFORM", lookbackBuckets: 4 });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.maxLookbackBuckets).toBe(3);
    expect(result.reason).toContain("at most 3 buckets");
    expect(result.reason).toContain("20-minute window");
  });

  it("uses one full-window partition for descriptive work", () => {
    const result = plan(MOE, 1, "DESCRIPTIVE");
    expect(result.partitions).toEqual([{ partition_id: "described", role: "DESCRIPTIVE",
      start: "2026-10-22T07:35:00Z", end: "2026-10-22T07:55:00Z" }]);
    expect(result.schedule.start).toBe("2026-10-22T07:40:00Z");
  });

  it("keeps every partition and the schedule ordered, aligned and inside the window", () => {
    for (const lookback of [1, 2, 3]) {
      const result = plan(MOE, lookback);
      let previous = MOE.start;
      for (const part of result.partitions) {
        expect(Date.parse(part.start)).toBe(Date.parse(previous));
        expect(Date.parse(part.end)).toBeGreaterThan(Date.parse(part.start));
        expect(Date.parse(part.start) % 300_000).toBe(0);
        expect(Date.parse(part.end) % 300_000).toBe(0);
        previous = part.end;
      }
      expect(Date.parse(result.partitions.at(-1)!.end)).toBe(Date.parse(MOE.end));
      expect(Date.parse(result.schedule.start)).toBeGreaterThanOrEqual(Date.parse(MOE.start));
      expect(Date.parse(result.schedule.end)).toBeLessThanOrEqual(Date.parse(MOE.end));
      expect(Date.parse(result.schedule.start) % 300_000).toBe(0);
      expect(Date.parse(result.schedule.end) % 300_000).toBe(0);
    }
  });

  it("refuses a window too short for the required three partitions", () => {
    const result = deriveHistoryPlan({ window: { start: "2026-10-22T07:35:00Z", end: "2026-10-22T07:45:00Z" },
      direction: "OUTPERFORM", lookbackBuckets: 1 });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toContain("too short");
  });
});

describe("historyUnknowns", () => {
  it("keeps the synthetic limits text unchanged", () => {
    expect(historyUnknowns("RECORDED_RESPONSE", null))
      .toEqual(["Recorded responses are synthetic; no real pool behaviour is measured."]);
  });

  it("names the providers and release for an actual source, and keeps the limits", () => {
    const text = historyUnknowns("PROVIDER_ACTUAL", "actual-moe-history-nansen-20261022/1")[0];
    expect(text).toContain("named providers");
    expect(text).toContain("actual-moe-history-nansen-20261022/1");
    expect(text).toContain("Costs are not modelled");
    expect(text).toContain("window is short");
    expect(text).not.toContain("synthetic");
  });
});
