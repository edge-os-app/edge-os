/**
 * #58 RESEARCH-PORTS-LOCAL, phase 1: on one saved request, declare an investigation on the source served through the
 * accepted P07 HTTP clients and save a Nansen token report, while no research worker runs. Both use the application's
 * AUTHORED transports: no network, no credential, no provider. Each browser width uses its own owner, so each pair of
 * jobs fits that owner's research budget. research-ports-report.spec.mjs continues after one worker pass.
 */
import { test, expect } from "@playwright/test";
import { apiGet, declare, historySection, noSeriousAxe, noSidewaysScroll, open, record, sample, shot } from "./research-flow.mjs";

const HTTP = "Native recording through the HTTP clients (authored transport, qualifies)";
export const TOKEN = "0xd8e004acba279417c04c0633cb5a21ceca207777";
const ownerToken = (project) => process.env[`P03_TOKEN_PORTS_${project.replace("-", "_").toUpperCase()}`];

test("declare on the HTTP-client source and save a Nansen report request", async ({ page }, info) => {
  const project = info.project.name;
  const token = ownerToken(project);
  expect(token, "the verifier mints one ports owner per width").toBeTruthy();
  await open(page, token);
  await sample(page, /I have no view/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNRESOLVED");
  const url = page.url();
  const intakeId = decodeURIComponent(url.split("/").pop() ?? "").split("?")[0];
  const section = await historySection(page, url);

  // The catalog lists the HTTP-client source as available on this composed server.
  const catalog = (await apiGet(page, token, "/v1/research/history-sources")).body;
  expect(catalog.source_clients).toBe("authored_http");
  expect(catalog.sources.find((item) => item.title === HTTP)?.available).toBe(true);
  const form = section.locator("details").filter({ hasText: "Declare a new recorded-history investigation" });
  if (!(await form.evaluate((node) => node.open))) await form.locator("summary").click();
  await form.getByLabel("Recorded source").selectOption({ label: HTTP });
  await expect(form.getByTestId("history-source-transport")).toContainText("accepted P07 HTTP clients over authored responses");
  await expect(form.getByLabel("Bound provider_requests")).toHaveValue("27");

  const hypothesis = `Rises keep rising through the HTTP clients (${project})`;
  const declarationId = await declare(section, { source: HTTP, hypothesis, providerRequests: "27",
    rules: [{ lookback: "1", threshold: "0", volume: "10" }] });
  const declared = (await apiGet(page, token, `/v1/research/requests/${intakeId}/history-investigations/${declarationId}`)).body;
  expect(declared.declaration.content.configuration.source.evidence_class).toBe("AUTHORED_HTTP_RESPONSE");
  await section.getByRole("button", { name: "Start investigation job" }).click();
  const job = section.getByTestId("history-job").first();
  await expect(job).toHaveAttribute("data-state", "RESERVED");
  await expect(job).toContainText("reserved 27");
  await shot(page, project, "p1-http-declared");

  // The Nansen report on the same request: the question is the saved request text, unchanged.
  const panel = page.getByTestId("nansen-report");
  await expect(panel.getByTestId("nansen-label")).toContainText("Not provider data");
  await panel.getByLabel("Token contract address").fill(TOKEN);
  await panel.getByLabel("Token symbol").fill("MOE");
  await panel.getByRole("button", { name: "Save and reserve this report" }).click();
  const nansenJob = panel.getByTestId("nansen-job").first();
  await expect(nansenJob).toHaveAttribute("data-state", "RESERVED");
  await expect(nansenJob).toContainText("No report yet.");
  const listed = (await apiGet(page, token, `/v1/research/requests/${intakeId}/nansen-reports`)).body.jobs;
  expect(listed).toHaveLength(1);
  expect(listed[0].budget.reserved.nansen_credits).toBe(12);
  await shot(page, project, "p2-nansen-reserved");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);
  record(`ports-${project}`, { url, intakeId, declarationId, hypothesis, nansenJobId: listed[0].job_id });
});
