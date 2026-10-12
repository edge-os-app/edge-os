/**
 * #58 RESEARCH-PORTS-LOCAL, phase 2, after one research worker pass: the HTTP-client job's saved dataset with its
 * labelled client facts, and the saved Nansen report reopened with the exact question, derived findings, gaps, coverage
 * and recomputed hashes. Another owner reads none of it. AUTHORED responses only; nothing reached a provider.
 */
import { test, expect } from "@playwright/test";
import { tokens } from "./fixture-auth.mjs";
import { apiGet, historySection, noSeriousAxe, noSidewaysScroll, open, openDeclaration, record, saved, shot } from "./research-flow.mjs";

const ownerToken = (project) => process.env[`P03_TOKEN_PORTS_${project.replace("-", "_").toUpperCase()}`];

test("HTTP-client dataset and reopened Nansen report; owner B denied", async ({ page }, info) => {
  const project = info.project.name;
  const token = ownerToken(project);
  const run = saved(`ports-${project}`);
  await open(page, token);
  const section = await historySection(page, run.url);
  await openDeclaration(section, run.hypothesis);
  const job = section.getByTestId("history-job").first();
  await expect(job).toHaveAttribute("data-state", "REPORTED");
  const facts = job.getByTestId("history-transport");
  await expect(facts).toContainText("through the accepted P07 HTTP clients (HttpEnvioQueryClient, HttpQuickNodeRpcClient), no network. Not provider data");
  await expect(facts).toContainText("receipt corroboration COMPLETE, 24 of 24 checked, 0 mismatches");
  await expect(facts).toContainText("ENVIO_HYPERSYNC 2, QUICKNODE_JSON_RPC 25");
  await expect(job).toContainText("provider usage MEASURED_CLIENT_CALLS");
  const report = job.getByTestId("history-report");
  await expect(report).toContainText("AUTHORED_HTTP_RESPONSE; SYNTHETIC_FIXTURE; verdict QUALIFIED");
  const datasetId = (await report.getByTestId("history-report-dataset").innerText()).trim();
  const dataset = (await apiGet(page, token, `/v1/research/history-datasets/${datasetId}`)).body;
  expect(dataset.hashes_verified).toEqual({ content_sha256: true, raw_evidence_sha256: true });
  expect(dataset.content.transport.transport_label).toBe("AUTHORED_HTTP_TRANSPORT");
  expect(JSON.stringify(dataset)).not.toContain("authored-local-fixture");
  await shot(page, project, "p3-http-report");

  // The saved Nansen report: the question is the saved request text, never rewritten.
  const request = (await apiGet(page, token, `/v1/research/requests/${run.intakeId}`)).body;
  const question = request.intake.content.original_request;
  const panel = page.getByTestId("nansen-report");
  const nansenJob = panel.getByTestId("nansen-job").first();
  await expect(nansenJob).toHaveAttribute("data-state", "REPORTED");
  await expect(nansenJob.getByTestId("nansen-job-answer")).toContainText("requests KNOWN 2 · credits KNOWN 6");
  await nansenJob.getByRole("button", { name: "Open saved report" }).click();
  const view = panel.getByTestId("nansen-report-view");
  await expect(view.getByTestId("nansen-question")).toHaveText(`Question: ${question}`);
  await expect(view.getByTestId("nansen-findings")).toContainText("Unresolved");
  await expect(view.getByTestId("nansen-coverage")).toContainText("3 holder address records (not people, not amounts)");
  await expect(view.getByTestId("nansen-coverage")).toContainText("24 of 24 flow periods");
  await expect(view.getByTestId("nansen-hashes")).toContainText("Saved hashes recomputed and matched. Evidence class AUTHORED_FIXTURE.");
  const jobView = (await apiGet(page, token, `/v1/research/investigation-jobs/${run.nansenJobId}`)).body;
  const reportId = jobView.nansen_report.report_id;
  const saved = (await apiGet(page, token, `/v1/research/nansen-reports/${reportId}`)).body;
  expect(saved.content.report.question).toBe(question);
  expect(Object.values(saved.hashes_verified).every(Boolean)).toBe(true);
  expect(jobView.budget.consumed.nansen_credits).toBe(6);
  expect(jobView.budget.unknown_liability.nansen_credits).toBe(0);
  await shot(page, project, "p4-nansen-report");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);

  // Another owner cannot read the report, its job, the request's report list or the dataset.
  for (const route of [`/v1/research/nansen-reports/${reportId}`, `/v1/research/investigation-jobs/${run.nansenJobId}`,
    `/v1/research/requests/${run.intakeId}/nansen-reports`, `/v1/research/history-datasets/${datasetId}`]) {
    expect((await apiGet(page, tokens.b, route)).status, route).toBe(404);
  }
  record(`ports-${project}`, { datasetId, reportId, reportSha256: saved.content_sha256, question });
});
