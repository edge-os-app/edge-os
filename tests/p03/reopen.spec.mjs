import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";
import { expectProvenanceFits, openProvenanceAndMeasure } from "./provenance-layout.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const results = JSON.parse(fs.readFileSync(path.join(evidence, "ui-results.json"), "utf8"));

// Run after the API process restarted. This browser context carries no storage from the first run.
test("after an API restart the saved rules reopen with their exact review text", async ({ page }, info) => {
  const savedRules = ["thesis", "volume-rule", "grouped-rule", "grouped-right", "tiny-threshold", "tiny-threshold-positive"]
    .map((name) => [name, results[`${name}-${info.project.name}`]]);
  expect(savedRules.every(([, saved]) => Boolean(saved)), "the first run must have saved every P06 rule").toBe(true);
  await injectAuth(page, tokens.a);
  const provenanceMeasurements = [];
  for (const [name, saved] of savedRules) {
    await page.goto(saved.url);
    await expect(page.getByTestId("revision-id")).toHaveText(saved.revisionId);
    await expect(page.getByTestId("original-request")).toHaveText(saved.original);
    await expect(page.getByTestId("revision")).toContainText("Read back from the database");
    if (saved.expectedEntry) await expect(page.getByTestId("rules-review")).toContainText(saved.expectedEntry);
    if (saved.expectedProvenance) {
      provenanceMeasurements.push(await openProvenanceAndMeasure(page, saved.expectedProvenance));
    }
    await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-${name}-reopened-after-restart.png`), fullPage: true });
  }
  provenanceMeasurements.forEach(expectProvenanceFits);
  const investigation = results[`investigation-${info.project.name}`];
  expect(investigation, "the first run must have saved a P08 declaration").toBeTruthy();
  await page.goto(investigation.url);
  await expect(page.getByTestId("investigation-saved")).toContainText(investigation.declarationId);
  await expect(page.getByLabel("I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.")).toHaveCount(0);
  await page.getByRole("button", { name: "Reopen saved declaration" }).click();
  await expect(page.getByTestId("investigation-saved")).toContainText("No study started");
  await expect(page.getByTestId("investigation-saved")).toContainText("DECLARATION_SAVED");
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-investigation-reopened-after-restart.png`), fullPage: true });
  expect(investigation.runId, "P09 must save its adopted run before the restart").toBeTruthy();
  await expect(page.getByTestId("effect-report-saved")).toContainText(investigation.reportId);
  const exactRun = await page.request.get(`${process.env.P03_API_URL}/v1/research/requests/${investigation.url.split("/research/").at(-1).split("?")[0]}/effect-runs/${investigation.runId}`,
    { headers: { Authorization: `Bearer ${tokens.a}` } });
  expect(exactRun.status()).toBe(200);
  const exactRunBody = await exactRun.json();
  expect(exactRunBody.report.record_id).toBe(investigation.reportId);
  expect(exactRunBody.report.content.result.statistical_status).toBe("UNRESOLVED");
  await page.getByRole("button", { name: "Reopen saved report without rerunning" }).click();
  await expect(page.getByTestId("effect-report-saved")).toContainText(investigation.reportId);
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-effect-report-reopened-after-restart.png`), fullPage: true });
});
