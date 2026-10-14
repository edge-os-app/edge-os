/**
 * #58 RESEARCH-RUNTIME-LOCAL, phase 3, after the release API and worker restart: the report, dataset, adopted revision
 * and replay reopen unchanged in a new browser context, and another owner sees none of it. Reopening calls nothing.
 * R58-RESEARCH-MOUNT-L2: the release Nansen report reopens with the same saved hash.
 */
import { test, expect } from "@playwright/test";
import { tokens } from "./fixture-auth.mjs";
import { apiGet, historySection, open, openDeclaration, saved, shot } from "./research-flow.mjs";

const ownerToken = (project) => process.env[`P03_TOKEN_RELEASE_${project.replace("-", "_").toUpperCase()}`];

test("the restarted release services reopen the exact report, dataset and replay", async ({ page }, info) => {
  const project = info.project.name;
  const token = ownerToken(project);
  const run = saved(`release-${project}`);
  await open(page, token);
  const section = await historySection(page, run.url);
  await openDeclaration(section, run.hypothesis);
  const job = section.getByTestId("history-job").first();
  await expect(job).toHaveAttribute("data-state", "REPORTED");
  await expect(job.getByTestId("history-report-id")).toHaveText(run.reportId);
  await expect(job.getByTestId("history-transport")).toContainText("Stand-in responses, not provider data; 27 request hashes kept");
  const report = await apiGet(page, token, `/v1/research/investigation-reports/${run.reportId}`);
  expect(report.body.stored_hash_matches_content).toBe(true);
  expect(report.body.content.evidence_class).toBe("RELEASE_STAND_IN_RESPONSE");
  const dataset = await apiGet(page, token, `/v1/research/history-datasets/${run.datasetId}`);
  expect(dataset.body.hashes_verified).toEqual({ content_sha256: true, raw_evidence_sha256: true });

  await page.goto(run.strategyUrl);
  await expect(page.getByTestId("revision-id")).toHaveText(run.releaseRevision);
  const replay = page.getByTestId("spot-replay");
  await replay.getByLabel("Saved replay ID").fill(run.replayId);
  await replay.getByRole("button", { name: "Load saved replay" }).click();
  await expect(replay.getByText("Loaded the exact saved result. The replay did not run again.")).toBeVisible();
  await expect(replay.getByTestId("spot-replay-history-lineage")).toContainText(run.datasetId);
  await shot(page, project, "r4-release-reopened");

  await historySection(page, run.url);  // the request page also holds the Nansen report panel
  const panel = page.getByTestId("nansen-report");
  const nansenJob = panel.getByTestId("nansen-job").first();
  await expect(nansenJob).toHaveAttribute("data-state", "REPORTED");
  await nansenJob.getByRole("button", { name: "Open saved report" }).click();
  await expect(panel.getByTestId("nansen-hashes")).toContainText("Saved hashes recomputed and matched.");
  const nansenReport = (await apiGet(page, token, `/v1/research/nansen-reports/${run.nansenReportId}`)).body;
  expect(nansenReport.content_sha256).toBe(run.nansenReportSha256);
  expect(nansenReport.content.transport_kind).toBe("LOOPBACK_HTTP");

  await open(page, tokens.b);
  await page.goto(run.url);
  await expect(page.getByText("This request was not found.")).toBeVisible();
  for (const route of [`/v1/research/investigation-jobs/${run.jobId}`, `/v1/research/investigation-reports/${run.reportId}`,
    `/v1/research/history-datasets/${run.datasetId}`, `/v1/spot-replays/${run.replayId}`,
    `/v1/research/requests/${run.intakeId}/history-investigations/${run.declarationId}`,
    `/v1/research/nansen-reports/${run.nansenReportId}`, `/v1/research/investigation-jobs/${run.nansenJobId}`]) {
    expect((await apiGet(page, tokens.b, route)).status, route).toBe(404);
  }
});
