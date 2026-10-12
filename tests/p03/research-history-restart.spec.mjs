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
