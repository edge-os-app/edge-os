/**
 * #58 SOURCE-LOCAL, phase 1: declare an investigation on a native-shaped recording and start its original job while
 * no research worker runs. The source is SYNTHETIC: native Envio pages and QuickNode results that the worker replays
 * through the accepted P07 transport with offline recorded clients. Each browser width uses its own owner, so each
 * job fits that owner's research budget. research-native-report.spec.mjs continues after one worker pass.
 */
import { test, expect } from "@playwright/test";
import { apiGet, declare, historySection, noSeriousAxe, noSidewaysScroll, open, record, sample, shot } from "./research-flow.mjs";

const NATIVE = "Native recording, full corroboration (qualifies)";
const ownerToken = (project) => process.env[`P03_TOKEN_NATIVE_${project.replace("-", "_").toUpperCase()}`];

test("declare on the native recording and start its original job", async ({ page }, info) => {
  const project = info.project.name;
  const token = ownerToken(project);
  expect(token, "the verifier mints one native owner per width").toBeTruthy();
  await open(page, token);
  await sample(page, /I have no view/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNRESOLVED");
  const url = page.url();
  const intakeId = decodeURIComponent(url.split("/").pop() ?? "").split("?")[0];
  const section = await historySection(page, url);

  const form = section.locator("details").filter({ hasText: "Declare a new recorded-history investigation" });
  if (!(await form.evaluate((node) => node.open))) await form.locator("summary").click();
  await form.getByLabel("Recorded source").selectOption({ label: NATIVE });
  await expect(form.getByTestId("history-source-transport")).toContainText("against recorded responses only");
  await expect(form.getByTestId("history-source-transport")).toContainText("It needs 27 provider requests");
  await expect(form.getByLabel("Bound provider_requests")).toHaveValue("27");

  const hypothesis = `Rises keep rising on the native recording (${project})`;
  const declarationId = await declare(section, { source: NATIVE, hypothesis, providerRequests: "27",
    rules: [{ lookback: "1", threshold: "0", volume: "10" }] });
  const saved = (await apiGet(page, token, `/v1/research/requests/${intakeId}/history-investigations/${declarationId}`)).body;
  expect(saved.declaration.content.configuration.source.evidence_class).toBe("RECORDED_NATIVE_RESPONSE");
  expect(saved.access_history[0].provider_queries).toBe(0);
  await shot(page, project, "n1-native-declared");

  await section.getByRole("button", { name: "Start investigation job" }).click();
  const job = section.getByTestId("history-job").first();
  await expect(job).toHaveAttribute("data-state", "RESERVED");
  await expect(job).toContainText("reserved 27");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);
  record(`native-${project}`, { url, intakeId, declarationId, hypothesis });
});
