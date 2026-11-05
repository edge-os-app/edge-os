import { describe, expect, it } from "vitest";
import { PROVIDER_USE, plain } from "../lib/labels";

describe("provider use labels", () => {
  it("does not show a known supplied count as Unknown", () => {
    expect(plain(PROVIDER_USE, "SUPPLIED_EVIDENCE", "Unknown")).toBe("supplied with the saved evidence");
  });

  it("does not show a malformed count as Unknown or as zero", () => {
    expect(plain(PROVIDER_USE, "INVALID", "Unknown")).toBe("invalid");
  });
});
