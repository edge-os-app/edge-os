import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";
import { expectProvenanceFits, openProvenanceAndMeasure } from "./provenance-layout.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const resultsFile = path.join(evidence, "ui-results.json");
const TINY_POSITIVE_THRESHOLD = `0.${"0".repeat(399)}1`;
const TINY_POSITIVE_RULE = `Enter when the 5-minute price return is above ${TINY_POSITIVE_THRESHOLD}. Exit when the 5-minute price return is below zero.`;
const EXPECTED_POSITIVE_MEANING = `Enter when price rose more than 0.${"0".repeat(397)}1% over the last 5 minutes`;

function record(key, value) {
  const current = JSON.parse(fs.readFileSync(resultsFile, "utf8"));
  current[key] = value;
  fs.writeFileSync(resultsFile, JSON.stringify(current, null, 2));
}

test("saved tiny-threshold provenance stays readable for both signs", async ({ page }, info) => {
  const project = info.project.name;
  const results = JSON.parse(fs.readFileSync(resultsFile, "utf8"));
  const negative = results[`tiny-threshold-${project}`];
  expect(negative, "the signed-out workflow must save the negative fixture first").toBeTruthy();

  await injectAuth(page, tokens.a);
  await page.goto(negative.url);
  await expect(page.getByTestId("revision-id")).toHaveText(negative.revisionId);
  const negativeMeasure = await openProvenanceAndMeasure(page, negative.expectedProvenance);
  await page.screenshot({ path: path.join(evidence, "screenshots", `${project}-tiny-negative-provenance-open.png`), fullPage: true });

  await page.goto("/");
  await page.getByLabel("Your words", { exact: true }).fill(TINY_POSITIVE_RULE);
  await page.getByRole("radio", { name: "Specific rule or thesis" }).check();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await expect(page.getByTestId("rules-review")).toContainText(EXPECTED_POSITIVE_MEANING);
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const positive = {
    url: page.url(),
    revisionId: (await page.getByTestId("revision-id").innerText()).trim(),
    original: TINY_POSITIVE_RULE,
    expectedEntry: EXPECTED_POSITIVE_MEANING,
    expectedProvenance: EXPECTED_POSITIVE_MEANING,
    expectedEntryTree: { op: "gt", args: [{ op: "price_return", lookback_buckets: 1 },
      { op: "constant", value: TINY_POSITIVE_THRESHOLD, unit: "DIMENSIONLESS" }] },
  };
  record(`tiny-threshold-positive-${project}`, positive);
  const positiveMeasure = await openProvenanceAndMeasure(page, positive.expectedProvenance);
  await page.screenshot({ path: path.join(evidence, "screenshots", `${project}-tiny-positive-provenance-open.png`), fullPage: true });

  // Defer layout assertions until both saved signs have rendered and been measured.
  expectProvenanceFits(negativeMeasure);
  expectProvenanceFits(positiveMeasure);
});
