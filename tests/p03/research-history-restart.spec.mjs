/**
 * #58 Task 6, phase 3 of 3, after an API and worker restart: the saved report, dataset, adopted revision and history
 * replay reopen unchanged in a new browser context; the retried job finished; another owner sees none of it.
 */
import { test, expect } from "@playwright/test";
import { tokens } from "./fixture-auth.mjs";
import { apiGet, historySection, open, openDeclaration, saved, shot } from "./research-flow.mjs";

test("restarted services reopen the exact research and replay records", async ({ page }, info) => {
  const project = info.project.name;
  const run = saved(`research-${project}`);
  await open(page, tokens.a);
  const section = await historySection(page, run.url);
  await openDeclaration(section, run.hypothesis);
  const cards = section.getByTestId("history-job");
  await expect(cards).toHaveCount(5);
  await expect(cards.nth(4)).toHaveAttribute("data-state", "REPORTED");
  await expect(cards.nth(0).getByTestId("history-report-id")).toHaveText(run.reportId);
  const report = await apiGet(page, tokens.a, `/v1/research/investigation-reports/${run.reportId}`);
  expect(report.status).toBe(200);
  expect(report.body.stored_hash_matches_content).toBe(true);
  const dataset = await apiGet(page, tokens.a, `/v1/research/history-datasets/${run.datasetId}`);
  expect(dataset.body.hashes_verified).toEqual({ content_sha256: true, raw_evidence_sha256: true });

  await page.goto(run.strategyUrl);
  await expect(page.getByTestId("revision-id")).toHaveText(run.historyRevision);
  const replay = page.getByTestId("spot-replay");
  await replay.getByLabel("Saved replay ID").fill(run.replayId);
  await replay.getByRole("button", { name: "Load saved replay" }).click();
  await expect(replay.getByText("Loaded the exact saved result. The replay did not run again.")).toBeVisible();
  await expect(replay.getByTestId("spot-replay-history-lineage")).toContainText(run.datasetId);
  await shot(page, project, "09-reopened");

  // Owner B cannot open owner A's request, job, report, dataset or replay.
  await open(page, tokens.b);
  await page.goto(run.url);
  await expect(page.getByText("This request was not found.")).toBeVisible();
  for (const route of [`/v1/research/investigation-jobs/${run.jobs.waiting}`, `/v1/research/investigation-reports/${run.reportId}`,
    `/v1/research/history-datasets/${run.datasetId}`, `/v1/spot-replays/${run.replayId}`,
    `/v1/research/requests/${run.intakeId}/history-investigations/${run.main}`]) {
    expect((await apiGet(page, tokens.b, route)).status, route).toBe(404);
  }
});

test("restarted services reopen the native report, transport facts and replay unchanged", async ({ page }, info) => {
  const project = info.project.name;
  const token = process.env[`P03_TOKEN_NATIVE_${project.replace("-", "_").toUpperCase()}`];
  const run = saved(`native-${project}`);
  await open(page, token);
  const section = await historySection(page, run.url);
  await openDeclaration(section, run.hypothesis);
  const job = section.getByTestId("history-job").first();
  await expect(job).toHaveAttribute("data-state", "REPORTED");
  await expect(job.getByTestId("history-transport")).toContainText("receipt corroboration COMPLETE, 24 of 24 checked, 0 mismatches");
  const dataset = await apiGet(page, token, `/v1/research/history-datasets/${run.datasetId}`);
  expect(dataset.body.hashes_verified).toEqual({ content_sha256: true, raw_evidence_sha256: true });
  expect(dataset.body.content.transport.client_calls).toEqual({ ENVIO_HYPERSYNC: 2, QUICKNODE_JSON_RPC: 25 });
  const replay = await apiGet(page, token, `/v1/spot-replays/${run.replayId}`);
  expect(replay.status).toBe(200);
  expect(replay.body.content.inputs.history_input.source_evidence_class).toBe("RECORDED_NATIVE_RESPONSE");
  expect((await apiGet(page, tokens.b, `/v1/spot-replays/${run.replayId}`)).status).toBe(404);
  await shot(page, project, "n4-native-reopened");
});

test("restarted services reopen the HTTP-client dataset and the Nansen report unchanged", async ({ page }, info) => {
  const project = info.project.name;
  const token = process.env[`P03_TOKEN_PORTS_${project.replace("-", "_").toUpperCase()}`];
  const run = saved(`ports-${project}`);
  await open(page, token);
  await page.goto(run.url);
  const panel = page.getByTestId("nansen-report");
  const nansenJob = panel.getByTestId("nansen-job").first();
  await expect(nansenJob).toHaveAttribute("data-state", "REPORTED");
  await nansenJob.getByRole("button", { name: "Open saved report" }).click();
  const view = panel.getByTestId("nansen-report-view");
  await expect(view.getByTestId("nansen-question")).toHaveText(`Question: ${run.question}`);
  await expect(view.getByTestId("nansen-hashes")).toContainText("Saved hashes recomputed and matched.");
  const report = (await apiGet(page, token, `/v1/research/nansen-reports/${run.reportId}`)).body;
  expect(report.content_sha256).toBe(run.reportSha256);
  // Reopening reads the saved report; it never bills or runs the transport again.
  const job = (await apiGet(page, token, `/v1/research/investigation-jobs/${run.nansenJobId}`)).body;
  expect(job.events.filter((event) => event.kind === "ATTEMPT_STARTED")).toHaveLength(1);
  const dataset = await apiGet(page, token, `/v1/research/history-datasets/${run.datasetId}`);
  expect(dataset.body.hashes_verified).toEqual({ content_sha256: true, raw_evidence_sha256: true });
  expect((await apiGet(page, tokens.b, `/v1/research/nansen-reports/${run.reportId}`)).status).toBe(404);
  await shot(page, project, "p5-ports-reopened");
});
