import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const results = JSON.parse(fs.readFileSync(path.join(evidence, "ui-results.json"), "utf8"));

// Run after the API process restarted. This browser context carries no storage from the first run.
test("after an API restart the saved rules reopen with their exact review text", async ({ page }, info) => {
  const savedRules = ["thesis", "volume-rule", "grouped-rule", "grouped-right", "tiny-threshold"]
    .map((name) => [name, results[`${name}-${info.project.name}`]]);
  expect(savedRules.every(([, saved]) => Boolean(saved)), "the first run must have saved every P06 rule").toBe(true);
  await injectAuth(page, tokens.a);
  for (const [name, saved] of savedRules) {
    await page.goto(saved.url);
    await expect(page.getByTestId("revision-id")).toHaveText(saved.revisionId);
    await expect(page.getByTestId("original-request")).toHaveText(saved.original);
    await expect(page.getByTestId("revision")).toContainText("Read back from the database");
    if (saved.expectedEntry) await expect(page.getByTestId("rules-review")).toContainText(saved.expectedEntry);
    await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-${name}-reopened-after-restart.png`), fullPage: true });
  }
});
