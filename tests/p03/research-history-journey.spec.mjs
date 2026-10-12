/**
 * #58 Task 6, phase 1 of 3: declare recorded-history investigations and start original jobs through the screens
 * while no research worker runs. Shows waiting, cancellation, retry as a new job and budget denial. The verifier then
 * stops one job like a killed worker and runs the worker once before research-history-report.spec.mjs.
 * SYNTHETIC recorded responses only.
 */
import { test, expect } from "@playwright/test";
import { tokens } from "./fixture-auth.mjs";
import { apiGet, declare, historySection, jobsFor, noSeriousAxe, noSidewaysScroll, open, record, sample, shot } from "./research-flow.mjs";

const QUALIFIED = "Synthetic recorded history (qualifies)";
const FAILING = "Synthetic recorded history (provider fails on page 2)";

test("declare first, then waiting, cancel, retry and budget denial", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await sample(page, /I have no view/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNRESOLVED");
  const url = page.url();
  const intakeId = decodeURIComponent(url.split("/").pop() ?? "").split("?")[0];
  const section = await historySection(page, url);
  await expect(section).toContainText("SYNTHETIC recording");
  await expect(section.getByTestId("research-budget")).toContainText("provider requests");

  const hypothesis = `Rises keep rising on the recorded pool (${project})`;
  const main = await declare(section, { source: QUALIFIED, hypothesis, rules: [
    { lookback: "1", threshold: "0", volume: "100" }, { lookback: "2", threshold: "0.004", volume: "101" }] });
  const declaration = (await apiGet(page, tokens.a, `/v1/research/requests/${intakeId}/history-investigations/${main}`)).body;
  expect(declaration.declaration.content.declaration_state).toBe("PRE_OUTCOME_DECLARED");
  expect(declaration.access_history[0].provider_queries).toBe(0);
  await shot(page, project, "01-declared");

  // The original job waits: the worker is not running, so nothing is collected yet.
  await section.getByRole("button", { name: "Start investigation job" }).click();
  await expect(section.getByText("Job saved and its budget reserved. It waits for the research worker.")).toBeVisible();
  const first = section.getByTestId("history-job").first();
  await expect(first).toHaveAttribute("data-state", "RESERVED");
  await expect(first).toContainText("Waiting for the research worker");
  await shot(page, project, "02-waiting");

  // A second job is cancelled while it waits, then retried as a new job.
  await section.getByRole("button", { name: "Start investigation job" }).click();
  await expect(section.getByTestId("history-job")).toHaveCount(2);
  await section.getByTestId("history-job").nth(1).getByRole("button", { name: "Cancel this job" }).click();
  await expect(section.getByTestId("history-job").nth(1)).toHaveAttribute("data-state", "CANCELLED");
  await expect(section.getByTestId("history-job").nth(1)).toContainText("released");
  await section.getByTestId("history-job").nth(1).getByRole("button", { name: "Retry as a new job" }).click();
  await expect(section.getByTestId("history-job")).toHaveCount(3);
  await expect(section.getByTestId("history-job").nth(2)).toHaveAttribute("data-state", "RESERVED");
  // A fourth job will be stopped by the verifier like a killed worker after its collection attempt starts.
  await section.getByRole("button", { name: "Start investigation job" }).click();
  await expect(section.getByTestId("history-job")).toHaveCount(4);
  await shot(page, project, "03-cancel-retry");
  const jobs = await jobsFor(page, tokens.a, intakeId, main);
  expect(jobs.map((job) => job.state)).toEqual(["RESERVED", "CANCELLED", "RESERVED", "RESERVED"]);
  expect(jobs[1].budget.released.provider_requests).toBe(2);

  // A declaration whose bounds exceed the owner's research budget is refused before any effect.
  const greedy = await declare(section, { source: QUALIFIED, hypothesis: `Greedy bounds (${project})`, providerRequests: "64",
    rules: [{ lookback: "3", threshold: "0.002", volume: "99" }] });
  await section.getByRole("button", { name: "Start investigation job" }).click();
  await expect(section.getByRole("alert")).toContainText("research budget cannot reserve");
  await expect(section.getByTestId("history-job").first()).toHaveAttribute("data-state", "BUDGET_EXHAUSTED");
  await shot(page, project, "04-budget-denied");

  // A source that fails on its second page is declared and waits too.
  const failing = await declare(section, { source: FAILING, hypothesis: `Provider loss case (${project})`,
    rules: [{ lookback: "1", threshold: "0.001", volume: "100" }] });
  await section.getByRole("button", { name: "Start investigation job" }).click();
  await expect(section.getByTestId("history-job").first()).toHaveAttribute("data-state", "RESERVED");
  const failingJobs = await jobsFor(page, tokens.a, intakeId, failing);
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);

  record(`research-${project}`, { url, intakeId, hypothesis, main, greedy, failing,
    jobs: { waiting: jobs[0].job_id, cancelled: jobs[1].job_id, retried: jobs[2].job_id, killed: jobs[3].job_id,
      failing: failingJobs[0].job_id } });
});
