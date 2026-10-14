/**
 * #58 RESEARCH-RUNTIME-LOCAL, phase 2, after one release worker pass: the job's saved dataset and report with the
 * stand-in labels, release identity and kept request hashes; market adoption as a NEW draft, publication and a
 * labelled replay with simulated fills. Another owner reads none of it. Stand-in responses only.
 * R58-RESEARCH-MOUNT-L2: the release Nansen report, collected over the accepted Nansen HTTP adapter from the loopback
 * stand-in, with its stand-in labels, saved hashes and KNOWN settlement.
 */
import { test, expect } from "@playwright/test";
import { tokens } from "./fixture-auth.mjs";
import { apiGet, historySection, noSeriousAxe, noSidewaysScroll, open, openDeclaration, record, sample, saved,
  shot } from "./research-flow.mjs";

const ownerToken = (project) => process.env[`P03_TOKEN_RELEASE_${project.replace("-", "_").toUpperCase()}`];
const SENTINELS = ["stand-in-bearer-SENTINEL-7d41c0", "stand-in-key-SENTINEL-55e0a1", "stand-in-nansen-SENTINEL-2b9c44"];

test("release report, stand-in facts, market adoption, publication and labelled replay", async ({ page }, info) => {
  const project = info.project.name;
  const token = ownerToken(project);
  const run = saved(`release-${project}`);
  await open(page, token);
  const section = await historySection(page, run.url);
  await openDeclaration(section, run.hypothesis);
  const job = section.getByTestId("history-job").first();
  await expect(job).toHaveAttribute("data-state", "REPORTED");
  const facts = job.getByTestId("history-transport");
  await expect(facts).toContainText("Operating release stand-in-loopback/1 through the accepted P07 HTTP clients (HttpEnvioQueryClient, HttpQuickNodeRpcClient) over loopback http.");
  await expect(facts).toContainText("Stand-in responses, not provider data; 27 request hashes kept; endpoint hosts 127.0.0.1, 127.0.0.1:");
  await expect(facts).toContainText("receipt corroboration COMPLETE, 24 of 24 checked, 0 mismatches");
  await expect(facts).toContainText("ENVIO_HYPERSYNC 2, QUICKNODE_JSON_RPC 25");
  await expect(job).toContainText("provider usage MEASURED_CLIENT_CALLS");
  const report = job.getByTestId("history-report");
  await expect(report).toContainText("RELEASE_STAND_IN_RESPONSE; SYNTHETIC_FIXTURE; verdict QUALIFIED");
  const datasetId = (await report.getByTestId("history-report-dataset").innerText()).trim();
  const reportId = (await report.getByTestId("history-report-id").innerText()).trim();
  const dataset = (await apiGet(page, token, `/v1/research/history-datasets/${datasetId}`)).body;
  expect(dataset.hashes_verified).toEqual({ content_sha256: true, raw_evidence_sha256: true });
  expect(dataset.content.transport_kind).toBe("LOOPBACK_HTTP");
  expect(dataset.content.operating_release.sha256).toBe(run.releaseSha256);
  expect(dataset.content.transport.request_sha256).toHaveLength(27);
  expect(dataset.content.application_collection_time.basis).toBe("APPLICATION_CLOCK");
  expect(SENTINELS.some((value) => JSON.stringify(dataset).includes(value))).toBe(false);
  await shot(page, project, "r2-release-report");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);
  for (const route of [`/v1/research/history-datasets/${datasetId}`, `/v1/research/investigation-jobs/${run.jobId}`,
    `/v1/research/investigation-reports/${reportId}`]) {
    expect((await apiGet(page, tokens.b, route)).status, route).toBe(404);
  }

  // The release Nansen report on the same request.
  const panel = page.getByTestId("nansen-report");
  const nansenJob = panel.getByTestId("nansen-job").first();
  await expect(nansenJob).toHaveAttribute("data-state", "REPORTED");
  await expect(nansenJob.getByTestId("nansen-job-answer")).toContainText("requests KNOWN 2 · credits KNOWN 6");
  await nansenJob.getByRole("button", { name: "Open saved report" }).click();
  const view = panel.getByTestId("nansen-report-view");
  await expect(view).toContainText("Stand-in Nansen-shaped responses served to the operating-release composition.");
  await expect(view.getByTestId("nansen-hashes")).toContainText("Saved hashes recomputed and matched.");
  await expect(view.getByTestId("nansen-hashes")).toContainText("Evidence class RELEASE_STAND_IN_RESPONSE.");
  const nansenReportId = (await apiGet(page, token, `/v1/research/investigation-jobs/${run.nansenJobId}`)).body
    .nansen_report.report_id;
  const nansenReport = (await apiGet(page, token, `/v1/research/nansen-reports/${nansenReportId}`)).body;
  expect(Object.values(nansenReport.hashes_verified).every(Boolean)).toBe(true);
  expect(nansenReport.content.evidence_class).toBe("RELEASE_STAND_IN_RESPONSE");
  expect(nansenReport.content.transport_kind).toBe("LOOPBACK_HTTP");
  expect(nansenReport.content.transport_label).toBe("RELEASE_STAND_IN_NANSEN_TRANSPORT");
  expect(nansenReport.content.operating_release.sha256).toBe(run.releaseSha256);
  expect(nansenReport.content.transport_response_sha256).toHaveLength(2);
  expect(nansenReport.content.settlement.provider_requests).toEqual({ state: "KNOWN", measured: 2, lost: 0 });
  expect(nansenReport.content.settlement.nansen_credits.state).toBe("KNOWN");
  expect(SENTINELS.some((value) => JSON.stringify(nansenReport).includes(value))).toBe(false);
  for (const route of [`/v1/research/nansen-reports/${nansenReportId}`, `/v1/research/investigation-jobs/${run.nansenJobId}`]) {
    expect((await apiGet(page, tokens.b, route)).status, route).toBe(404);
  }
  await shot(page, project, "r2-release-nansen-report");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);
  record(`release-${project}`, { nansenReportId, nansenReportSha256: nansenReport.content_sha256 });

  // A strategy request on the same owner: save the fixture-market revision, then adopt the release dataset's market.
  await page.goto("/");
  await sample(page, "Specific thesis").click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const fixtureRevision = (await page.getByTestId("revision-id").innerText()).trim();
  const adoption = page.getByTestId("market-adoption");
  await adoption.getByLabel("Saved dataset").selectOption(datasetId);
  const reviewBox = adoption.getByTestId("market-adoption-review");
  await expect(reviewBox).toContainText("0x" + "d1".repeat(20));
  await expect(reviewBox).toContainText("RELEASE_STAND_IN_RESPONSE");
  await adoption.getByLabel("Trade size in the new quote unit").fill("50");
  await adoption.getByLabel("Largest position value in the new quote unit").fill("50");
  const declaredRule = (await apiGet(page, token, "/v1/research/history-datasets")).body.datasets
    .find((item) => item.dataset_id === datasetId).declared_rules[0];
  await adoption.getByLabel("Entry rule (one you declared for this dataset)").selectOption(declaredRule.evaluation_id);
  await adoption.getByLabel("Exit lookback (buckets)").fill("2");
  await adoption.getByLabel("Exit threshold (fraction, for example -0.001)").fill("-0.001");
  await adoption.getByRole("checkbox").check();
  await adoption.getByRole("button", { name: "Adopt this market for a new draft" }).click();
  await expect(adoption.getByRole("status")).toContainText("uses the recorded market");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const releaseRevision = (await page.getByTestId("revision-id").innerText()).trim();
  expect(releaseRevision).not.toBe(fixtureRevision);
  const strategyUrl = page.url();

  const replay = page.getByTestId("spot-replay");
  await replay.getByLabel("Price data").selectOption(datasetId);
  await expect(replay.getByTestId("spot-replay-history-source")).toContainText("Simulated fills");
  for (let step = 0; step < 3; step += 1) await replay.getByRole("button", { name: "Add entry dependency" }).click();
  await replay.getByLabel("entry dependency offset 2").fill("-1");
  await replay.getByLabel("entry dependency series 3").selectOption("quote_volume");
  await replay.getByRole("button", { name: "Add exit dependency" }).click();
  await replay.getByRole("button", { name: "Add exit dependency" }).click();
  await replay.getByLabel("exit dependency offset 2").fill("-2");
  await replay.getByLabel("I reviewed the entry dependency set").check();
  await replay.getByLabel("I reviewed the exit dependency set").check();
  await replay.getByRole("button", { name: "Save replay on recorded history" }).click();
  const result = replay.getByTestId("spot-replay-result");
  await expect(result).toContainText("Saved replay: complete");
  await expect(result).toContainText("Simulated fills on saved recorded-history dataset");
  await expect(replay.getByTestId("spot-replay-history-lineage")).toContainText(run.declarationId);
  const replayId = (await replay.getByTestId("spot-replay-id").innerText()).trim();
  const savedReplay = (await apiGet(page, token, `/v1/spot-replays/${replayId}`)).body;
  expect(savedReplay.content.inputs.history_input.source_evidence_class).toBe("RELEASE_STAND_IN_RESPONSE");
  expect(savedReplay.content.inputs.history_input.fill_label).toBe("simulated fills");
  expect((await apiGet(page, tokens.b, `/v1/spot-replays/${replayId}`)).status).toBe(404);
  await shot(page, project, "r3-release-replay");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);
  record(`release-${project}`, { datasetId, reportId, releaseRevision, replayId, strategyUrl });
});
