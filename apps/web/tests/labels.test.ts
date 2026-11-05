import { describe, expect, it } from "vitest";
import { DATASET_LIMIT, EVALUATION_OUTCOME, PROVIDER_USE, deliveryCheckText, plain } from "../lib/labels";

describe("provider use labels", () => {
  it("does not show a known supplied count as Unknown", () => {
    expect(plain(PROVIDER_USE, "SUPPLIED_EVIDENCE", "Unknown")).toBe("supplied with the saved evidence");
  });

  it("does not show a malformed count as Unknown or as zero", () => {
    expect(plain(PROVIDER_USE, "INVALID", "Unknown")).toBe("invalid");
  });
});

describe("job outcome labels", () => {
  it.each(["REVALIDATION_DENIED", "SUBMISSION_NOT_OWNED", "CLAIMED", "BREACHED", "RECONCILE_MISMATCH"])(
    "states the queue outcome %s instead of an unknown state", (code) => {
      expect(plain(EVALUATION_OUTCOME, code, "Unknown state")).not.toBe("Unknown state");
    });
});

describe("delivery check text", () => {
  it("does not call data unusable when no check is required", () => {
    for (const status of ["NOT_REQUIRED", null, undefined]) {
      expect(deliveryCheckText(status)).toBe("This saved data needs no delivery check.");
    }
  });

  it("separates an unfinished check from a mismatch", () => {
    expect(deliveryCheckText("INCOMPLETE")).toContain("did not finish");
    expect(deliveryCheckText("INCOMPLETE")).not.toContain("does not match");
    expect(deliveryCheckText("MISMATCH")).toContain("does not match the recorded delivery");
  });

  it("refuses use for an unmapped state", () => {
    expect(deliveryCheckText("NEW_STATE")).toContain("Do not use this data");
  });
});

describe("saved data limits", () => {
  it.each(["SOURCE_UNAVAILABLE", "PARTIAL_COVERAGE", "VERDICT_LIMITED", "VERDICT_UNRESOLVED"])("names %s", (code) => {
    expect(DATASET_LIMIT[code]).toBeTruthy();
  });
});
