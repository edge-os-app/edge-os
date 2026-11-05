import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SPEC_DIRS = ["../../../tests/p03", "../../../tests/deployment_rehearsal/browser"].map((dir) => resolve(import.meta.dirname, dir));

/** UI text the plain-copy change removed. A browser spec that still looks for one of these cannot pass. */
const RETIRED = [
  "Add entry dependency",
  "Add exit dependency",
  "I reviewed the entry dependency set",
  "I reviewed the exit dependency set",
  "Save synthetic replay",
  "Save replay on recorded history",
  "Adopt and save declaration",
  "Reopen saved declaration",
  "Open this declaration",
  "Save history declaration",
  "Declare trading and gas assets",
  "Save reviewed deposit",
  "Run one bounded evaluation",
  "Saved, not dispatched",
  "Cancelled before dispatch",
  "authored local fixture",
  "Capital flow, not trading profit.",
  "ACTIVE AT APPLICATION",
];

describe("browser specs", () => {
  it("do not look for retired UI text", () => {
    const specs = SPEC_DIRS.flatMap((dir) => readdirSync(dir, { recursive: true, encoding: "utf8" })
      .filter((name) => name.endsWith(".mjs")).map((name) => join(dir, name)));
    expect(specs.length).toBeGreaterThan(0);
    const found = specs.flatMap((file) => RETIRED.filter((text) => readFileSync(file, "utf8").includes(text)).map((text) => `${file}: ${text}`));
    expect(found).toEqual([]);
  });
});
