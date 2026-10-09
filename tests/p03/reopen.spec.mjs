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
  await expect(replayPanel.getByRole("heading", { name: "Simulated replay summary" })).toBeVisible();
  const reopenedChart = replayPanel.getByRole("img", { name: "Account balance in quote over the replay window" });
  await expect(reopenedChart).toBeVisible();
  const savedInputs = replayPanel.getByTestId("spot-replay-saved-inputs");
  await expect(savedInputs).toContainText(replay.revisionId);
  await expect(savedInputs).toContainText("p13-config-");
  await expect(savedInputs).toContainText("p13.wc01/1");
  await expect(savedInputs).toContainText("2026-10-01 12:05:00 UTC to 2026-10-01 12:35:00 UTC");
  await expect(savedInputs).toContainText("1000 quote cash");
  await expect(savedInputs).toContainText("100 QUOTE:0x2222222222222222222222222222222222222222");
  await expect(savedInputs).toContainText("3 scheduled buckets");
  await expect(savedInputs).toContainText("synthetic:adopted-cost-profile");
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
  expect(exactReplayBody.content.result.samples).toEqual(replay.expectedSamples);
  expect(exactReplayBody.content.result.metrics).toEqual(replay.expectedMetrics);
  const reopenedSampleList = replayPanel.getByRole("list", { name: "Saved account value samples" });
  for (const sample of exactReplayBody.content.result.samples) {
    if (sample.account_value_quote === null) {
      await expect(reopenedSampleList).toContainText("Unavailable");
      for (const reason of sample.mark_reasons ?? []) await expect(reopenedSampleList).toContainText(reason);
    } else {
      await expect(reopenedSampleList).toContainText(sample.account_value_quote);
    }
  }
  const reopenedSummary = await replayPanel.locator(".spot-replay-summary").innerText();
  for (const [metric, value] of Object.entries(exactReplayBody.content.result.metrics)) {
    if (value !== null && exactReplayBody.content.result.metric_statuses[metric] === "AVAILABLE") {
      expect(reopenedSummary).toContain(String(value));
    }
  }
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

  const unavailableCases = [
    ["unbound-entry", "UNRESOLVED_ESSENTIAL_EVIDENCE", "UNBOUND: dependency list is null"],
    ["bound-exit-null", "INVALID_ESSENTIAL_BINDING", "BOUND: dependency list is null"],
  ];
  for (const [name, reason, summary] of unavailableCases) {
    const unavailable = results[`spot-replay-unavailable-${name}-${info.project.name}`];
    expect(unavailable, `the first browser drive must save ${name}`).toBeTruthy();
    await replayPanel.getByLabel("Saved replay ID").fill(unavailable.replayId);
    await replayPanel.getByRole("button", { name: "Load saved replay" }).click();
    await expect(replayPanel.getByTestId("spot-replay-id")).toHaveText(unavailable.replayId);
    await expect(replayPanel.getByTestId("spot-replay-result")).toContainText("Saved replay: unavailable");
    await expect(replayPanel.getByRole("alert")).toContainText(reason);
    await expect(replayPanel.getByTestId("spot-replay-saved-inputs")).toContainText(summary);
    await expect(replayPanel.getByRole("img", { name: "Account balance in quote over the replay window" })).toBeVisible();
    await expect(replayPanel.getByText("No saved balance samples are available.")).toBeVisible();
    const exactUnavailable = await page.request.get(`${process.env.P03_API_URL}/v1/spot-replays/${unavailable.replayId}`,
      { headers: { Authorization: `Bearer ${tokens.a}` } });
    expect(exactUnavailable.status()).toBe(200);
    const unavailableBody = await exactUnavailable.json();
    expect(unavailableBody.replay_id).toBe(unavailable.replayId);
    expect(unavailableBody.content_sha256).toBe(unavailable.replayHash);
    expect(unavailableBody.content.result.status).toBe("UNAVAILABLE");
    expect(unavailableBody.content.result.reason.code).toBe(reason);
    expect(unavailableBody.content.inputs.essential_evidence.fields.entry.essential_dependencies ?? null)
      .toEqual(unavailable.expectedEntryDependencies);
    expect(unavailableBody.content.inputs.essential_evidence.fields.exit.essential_dependencies ?? null)
      .toEqual(unavailable.expectedExitDependencies);
    await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-${name}-reopened-after-restart.png`), fullPage: true });
  }
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-spot-replay-reopened-after-restart.png`), fullPage: true });
  expect(createReplayRequests, "all P13 reopen paths after restart must only retrieve, never recompute").toBe(0);

  const p19 = results[`p19-context-${info.project.name}`];
  expect(p19, "the first browser drive must exercise mounted P19 context controls at both viewports").toBeTruthy();
  let p19Writes = 0;
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (request.method() !== "GET" && (pathname.startsWith("/v1/account-views") || pathname.startsWith(`/v1/agents/${p19.agentId}/context`))) p19Writes += 1;
  });
  await page.goto(p19.url);
  await expect(page.getByRole("heading", { name: "Account", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: p19.agentId, level: 2 })).toBeVisible();
  await expect(page.locator(`#record-${p19.agentRecordId}`)).toBeVisible();
  const reopenedAgent = page.locator("section.panel").filter({ has: page.getByRole("heading", { name: p19.agentId, level: 2 }) });
  await reopenedAgent.getByRole("button", { name: "Inspect agent context" }).click();
  const persistedContext = page.getByRole("region", { name: `${p19.agentId} context` });
  await expect(persistedContext).toContainText("Agent context · version 5");
  await expect(persistedContext).toContainText("CLEARED");
  await expect(persistedContext.getByRole("listitem")).toHaveCount(0);
  const exactContext = await page.request.get(`${process.env.P03_API_URL}/v1/agents/${p19.agentId}/context`, {
    headers: { Authorization: `Bearer ${tokens.a}` },
  });
  expect(exactContext.status()).toBe(200);
  expect(await exactContext.json()).toMatchObject({ memory_version: 5, state: "CLEARED", entries: [] });
  const exactAccounts = await page.request.get(`${process.env.P03_API_URL}/v1/account-views?limit=500`, {
    headers: { Authorization: `Bearer ${tokens.a}` },
  });
  expect(exactAccounts.status()).toBe(200);
  const persistedAccounts = await exactAccounts.json();
  expect(persistedAccounts.records).toHaveLength(Number(process.env.P19_ACCOUNT_RECORD_COUNT));
  expect(persistedAccounts.records.map((row) => row.record_id)).toContain(p19.agentRecordId);
  const resolvedSource = await page.request.get(`${process.env.P03_API_URL}/v1/account-views/source/${p19.researchSourceId}`, {
    headers: { Authorization: `Bearer ${tokens.a}` },
  });
  expect(resolvedSource.status()).toBe(200);
  expect(await resolvedSource.json()).toMatchObject({ source_record_type: "IntakeRequest", destination_type: "RESEARCH",
    destination_record_id: p19.researchSourceId });
  const reopenedResearch = await page.request.get(`${process.env.P03_API_URL}/v1/research/requests/${p19.researchSourceId}`, {
    headers: { Authorization: `Bearer ${tokens.a}` },
  });
  expect(reopenedResearch.status()).toBe(200);
  await page.goto(`${process.env.P03_WEB_URL}/#/agents?record=${p19.sourceActionId}`);
  const restartedSourceAction = page.locator(`#record-${p19.sourceActionId}`);
  const restartedSourcePosition = page.locator(`#record-${p19.sourcePositionId}`);
  await expect(restartedSourceAction).toHaveCount(1);
  await expect(restartedSourceAction).toBeVisible();
  await expect(restartedSourcePosition).toHaveCount(1);
  await expect(restartedSourcePosition).toBeVisible();
  await expect(restartedSourcePosition).toContainText(p19.agentId === "agent-a" ? "action-a-failed-2 · REVERTED" : "action-b-failed-paged · REVERTED");
  for (const [name, sourceId] of Object.entries(p19.orphanSourceIds)) {
    const exactSourceResponse = await page.request.get(`${process.env.P03_API_URL}/v1/account-views/${sourceId}`, {
      headers: { Authorization: `Bearer ${tokens.a}` },
    });
    expect(exactSourceResponse.status()).toBe(200);
    const source = await exactSourceResponse.json();
    expect(source.record_id).toBe(sourceId);
    const exactSourceResolver = await page.request.get(`${process.env.P03_API_URL}/v1/account-views/source/${sourceId}`, {
      headers: { Authorization: `Bearer ${tokens.a}` },
    });
    expect(exactSourceResolver.status()).toBe(200);
    expect((await exactSourceResolver.json()).destination_record_id).toBe(sourceId);
    await page.goto(`${process.env.P03_WEB_URL}/#/agents?record=${sourceId}`);
    const reopenedExactSource = page.locator(`#record-${sourceId}`);
    await expect(reopenedExactSource).toHaveCount(1);
    await expect(reopenedExactSource).toBeVisible();
    for (const value of [source.owner_id, source.content.agent_id, source.content.wallet_id,
      source.content.network_id, source.content.strategy_revision, source.content.mandate_id,
      source.content.status, source.content.updated_at]) await expect(reopenedExactSource).toContainText(value);
    if (source.content.record_kind === "MONITORING") {
      await expect(reopenedExactSource).toContainText(source.content.next_work);
      await expect(reopenedExactSource).toContainText(source.content.blocking_reason);
      await expect(reopenedExactSource).toContainText(`${source.content.evaluation_attempts} attempts / ${source.content.evaluation_completions} completions`);
    } else {
      await expect(reopenedExactSource).toContainText(source.content.approval_id);
      await expect(reopenedExactSource).toContainText(source.content.terms_hash);
      await expect(reopenedExactSource).toContainText(source.content.signer_binding);
      await expect(reopenedExactSource).toContainText(source.content.policy_binding);
      for (const value of [source.content.terms.expiry, ...source.content.terms.supported_assets,
        ...source.content.terms.supported_routes, ...source.content.terms.actions, ...source.content.terms.stop_effects])
        await expect(reopenedExactSource).toContainText(value);
    }
    await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-${name}-source-reopened-after-restart.png`), fullPage: true });
  }
  expect(p19Writes, "reopen after API restart must only issue reads").toBe(0);
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-p19-account-context-reopened-after-restart.png`), fullPage: true });
});
