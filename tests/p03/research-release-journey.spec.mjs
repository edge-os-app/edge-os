/**
 * #58 RESEARCH-RUNTIME-LOCAL, phase 1: the API composes a STAND-IN operating release served by an owned loopback
 * stand-in provider. Declare on its one source with the release's fixed bounds and start one job while no research
 * worker runs. Nothing reaches a real provider. research-release-report.spec.mjs continues after one worker pass.
 */
import { test, expect } from "@playwright/test";
import { apiGet, declare, historySection, noSeriousAxe, noSidewaysScroll, open, record, sample, shot } from "./research-flow.mjs";

const SOURCE = "Stand-in release over native-syn-qualified/1 (not provider data)";
const ownerToken = (project) => process.env[`P03_TOKEN_RELEASE_${project.replace("-", "_").toUpperCase()}`];

test("declare on the operating-release source with its fixed bounds and start one job", async ({ page }, info) => {
  const project = info.project.name;
  const token = ownerToken(project);
  expect(token, "the verifier mints one release owner per width").toBeTruthy();
  await open(page, token);
  await sample(page, /I have no view/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNRESOLVED");
  const url = page.url();
  const intakeId = decodeURIComponent(url.split("/").pop() ?? "").split("?")[0];
  const section = await historySection(page, url);

  const catalog = (await apiGet(page, token, "/v1/research/history-sources")).body;
  expect(catalog.operating_release.kind).toBe("STAND_IN");
  const entry = catalog.sources.find((item) => item.title === SOURCE);
  expect(entry.available).toBe(true);
  expect(entry.evidence_class).toBe("RELEASE_STAND_IN_RESPONSE");
  const form = section.locator("details").filter({ hasText: "Declare a new recorded-history investigation" });
  if (!(await form.evaluate((node) => node.open))) await form.locator("summary").click();
  await form.getByLabel("Recorded source").selectOption({ label: SOURCE });
  const release = form.getByTestId("history-source-release");
  await expect(release).toContainText("Operating release stand-in-loopback/1 (stand-in), RELEASE_STAND_IN_RESPONSE.");
  await expect(release).toContainText("Stand-in responses on this server (loopback http), not provider data.");
  await expect(release).toContainText("27 provider requests, 2 pages, 200 rows");
  await expect(release).toContainText("Endpoint hosts: 127.0.0.1, 127.0.0.1. Credentials stay on the server.");
  await expect(form.getByLabel("Bound provider_requests")).toHaveValue("27");
  await expect(form.getByLabel("Bound provider_requests")).toHaveAttribute("readonly", "");

  const hypothesis = `Rises keep rising under the stand-in release (${project})`;
  const declarationId = await declare(section, { source: SOURCE, hypothesis, providerRequests: null,
    rules: [{ lookback: "1", threshold: "0", volume: "10" }] });
  const declared = (await apiGet(page, token, `/v1/research/requests/${intakeId}/history-investigations/${declarationId}`)).body;
  expect(declared.declaration.content.configuration.source.evidence_class).toBe("RELEASE_STAND_IN_RESPONSE");
  expect(declared.declaration.content.configuration.resource_bounds).toEqual(entry.release.history.limits);
  expect(declared.declaration.content.frozen.operating_release_sha256).toBe(catalog.operating_release.sha256);
  await expect(section.getByTestId("history-declaration-release")).toContainText(`stand-in-loopback/1 · ${catalog.operating_release.sha256}`);
  await section.getByRole("button", { name: "Start investigation job" }).click();
  const job = section.getByTestId("history-job").first();
  await expect(job).toHaveAttribute("data-state", "RESERVED");
  await expect(job).toContainText("reserved 27");
  const jobs = (await apiGet(page, token, `/v1/research/requests/${intakeId}/history-investigations/${declarationId}/jobs`)).body.jobs;
  expect(jobs).toHaveLength(1);
  await shot(page, project, "r1-release-declared");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);
  record(`release-${project}`, { url, intakeId, declarationId, hypothesis, jobId: jobs[0].job_id,
    releaseSha256: catalog.operating_release.sha256 });
});
