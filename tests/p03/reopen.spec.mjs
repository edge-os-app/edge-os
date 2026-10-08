import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const results = JSON.parse(fs.readFileSync(path.join(evidence, "ui-results.json"), "utf8"));

// Run after the API process restarted. A new browser context carries no storage from the first run.
test("after an API restart the saved revision reopens unchanged", async ({ page }, info) => {
  const saved = results[`thesis-${info.project.name}`];
  expect(saved, "the first run must have saved a revision").toBeTruthy();
  await injectAuth(page, tokens.a);
  await page.goto(saved.url);
  await expect(page.getByTestId("revision-id")).toHaveText(saved.revisionId);
  await expect(page.getByTestId("original-request")).toHaveText(saved.original);
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-09-reopened-after-restart.png`), fullPage: true });
});
