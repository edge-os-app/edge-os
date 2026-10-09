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

  const replay = results[`spot-replay-${info.project.name}`];
  expect(replay, "the first browser drive must save a P13 synthetic replay").toBeTruthy();
  let createReplayRequests = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/v1/spot-replays") createReplayRequests += 1;
  });
  await page.goto(replay.url);
  const replayPanel = page.getByTestId("spot-replay");
  await replayPanel.getByLabel("Saved replay ID").fill(replay.replayId);
  await replayPanel.getByRole("button", { name: "Load saved replay" }).click();
  await expect(replayPanel.getByTestId("spot-replay-id")).toHaveText(replay.replayId);
  await expect(replayPanel.getByTestId("spot-replay-result")).toContainText(replay.replayHash);
  await expect(replayPanel.getByTestId("spot-replay-result")).toContainText(replay.expectedEndingCashQuote);
  const savedInputs = replayPanel.getByTestId("spot-replay-saved-inputs");
  await expect(savedInputs).toContainText(replay.revisionId);
  await expect(savedInputs).toContainText("p13-config-");
  await expect(savedInputs).toContainText("p13.wc01/1");
  await expect(savedInputs).toContainText("2026-10-01 12:05:00 UTC to 2026-10-01 12:35:00 UTC");
  await expect(savedInputs).toContainText("1000 quote cash");
  await expect(savedInputs).toContainText("100 QUOTE:0x2222222222222222222222222222222222222222");
  await expect(savedInputs).toContainText("3 scheduled buckets");
  await expect(savedInputs).toContainText("p02.cost-assumptions");
  await expect(savedInputs).toContainText("price@0, price@-3");
  await expect(savedInputs).toContainText("price@0, price@-1");
  await expect(replayPanel).toContainText("Loaded the exact saved result. The replay did not run again.");
  expect(createReplayRequests, "reopening after restart must only retrieve, never recompute").toBe(0);
  const exactReplay = await page.request.get(`${process.env.P03_API_URL}/v1/spot-replays/${replay.replayId}`,
    { headers: { Authorization: `Bearer ${tokens.a}` } });
  expect(exactReplay.status()).toBe(200);
  const exactReplayBody = await exactReplay.json();
  expect(exactReplayBody.replay_id).toBe(replay.replayId);
  expect(exactReplayBody.content_sha256).toBe(replay.replayHash);
  expect(exactReplayBody.content.inputs.essential_evidence.fields.entry.essential_dependencies)
    .toEqual(replay.expectedEntryDependencies);
  expect(exactReplayBody.content.inputs.essential_evidence.fields.exit.essential_dependencies)
    .toEqual(replay.expectedExitDependencies);
  const saved = exactReplayBody.content.inputs;
  const visible = await savedInputs.innerText();
  const displayUtc = (value) => {
    const iso = new Date(value).toISOString();
    return `${iso.slice(0, 10)} ${iso.slice(11, 19)} UTC`;
  };
  for (const value of [saved.profile_version, saved.strategy_revision_id, saved.run_configuration_id,
    saved.dataset_fixture_id, saved.dataset_revision_id, displayUtc(saved.window_start), displayUtc(saved.window_end),
    saved.initial_cash_quote, saved.initial_base_amount, saved.initial_basis_quote,
    saved.strategy.sizing.amount, saved.strategy.sizing.unit, String(saved.strategy.warmup_buckets),
    saved.strategy.cost_assumptions.source_ref, saved.strategy.cost_assumptions.fee_rate,
    saved.strategy.cost_assumptions.slippage_rate]) {
    expect(visible).toContain(value);
  }
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-spot-replay-reopened-after-restart.png`), fullPage: true });
});
