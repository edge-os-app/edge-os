/**
 * #58 P27 LOCAL, phase 1: each browser width is its own owner. Through the real screens it saves a revision, sets up
 * and funds the agent wallet, adopts exact terms and explicitly starts recurring operation. The browser then closes;
 * scripts/p03/recurring_phase.py runs separate producer processes with no browser or HTTP caller, and
 * recurring-report.spec.mjs reopens the saved outcome. The desktop agent trades normally; the 390px agent's actions
 * lose their acknowledgement (fixture marker) so each stays unknown until the producer reconciles its receipt.
 * Authored fixture ports only: nothing is a wallet, deposit, quote, transaction or chain evidence.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
const resultsFile = path.join(evidence, "recurring-results.json");
const TRADING = "1000000000";
const GAS = "1000000000000000000";

const ownerToken = (project) => process.env[`P03_TOKEN_REC_${project.replace("-", "_").toUpperCase()}`];
const agentFor = (project) => (project === "desktop" ? "rec-desktop" : "rec-mobile-390-fx-lost-ack");

function record(key, value) {
  const saved = fs.existsSync(resultsFile) ? JSON.parse(fs.readFileSync(resultsFile, "utf8")) : {};
  saved[key] = { ...(saved[key] ?? {}), ...value };
  fs.writeFileSync(resultsFile, JSON.stringify(saved, null, 2));
}

async function shot(page, project, name) {
  fs.mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, `${project}-rec-${name}.png`), fullPage: true });
}

async function noSidewaysScroll(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "no sideways scroll").toBeLessThanOrEqual(0);
}

async function noSeriousAxe(page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
}

test("save a revision, set up the agent wallet, adopt terms and start recurring operation", async ({ page }, info) => {
  const project = info.project.name;
  const token = ownerToken(project);
  expect(token, "the verifier mints one recurring owner per width").toBeTruthy();
  const agentId = agentFor(project);
  await injectAuth(page, token);
  await page.goto("/");
  await expect(page.getByTestId("fixture-banner")).toContainText("TEST AUTH FIXTURE");

  // A revision of this owner's own thesis.
  await page.locator("button.example", { hasText: "Specific thesis" }).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const thesisUrl = page.url();

  // Wallet setup and funding (authored fixtures).
  const setup = page.getByRole("region", { name: "Agent wallet setup" });
  await setup.getByLabel("Agent ID").fill(agentId);
  await setup.getByRole("button", { name: "Check saved setup" }).click();
  await setup.getByRole("button", { name: "Save wallet setup" }).click();
  await setup.getByRole("button", { name: "Create wallet now" }).click();
  await expect(setup.getByTestId("wallet-setup-state")).toHaveText("Wallet confirmed");
  await setup.getByRole("link", { name: "Fund this agent" }).click();
  const funding = page.getByRole("region", { name: "Agent funding" });
  await funding.getByRole("button", { name: "Declare trading and gas assets" }).click();
  for (const [label, raw] of [["Trading capital", TRADING], ["Native MON gas", GAS]]) {
    await funding.getByLabel("Asset").selectOption({ label });
    await funding.getByLabel(/Amount in base units/).fill(raw);
    await funding.getByRole("button", { name: "Save reviewed deposit" }).click();
    await expect(funding.getByTestId("funding-flows")).toContainText("PENDING");
  }
  await funding.getByRole("button", { name: "Check deposits" }).click();
  await expect(funding.getByTestId("funding-credited")).toContainText("1000 credited");

  // Exact terms, adopted inactive; the server derives the fixture qualification.
  await page.goto(`/#/agents?agent=${encodeURIComponent(agentId)}`);
  const authority = page.getByRole("region", { name: "Agent authority" });
  await authority.getByRole("button", { name: "Review exact terms" }).click();
  await authority.getByRole("button", { name: "Adopt these exact terms (inactive)" }).click();
  await expect(authority.getByTestId("activation-state")).toContainText("SYNTHETIC_FIXTURE_QUALIFICATION");

  // Explicit recurring authorization, bound to the exact adopted terms.
  await page.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
  const recurring = page.getByRole("region", { name: "Recurring operation" });
  const start = recurring.getByRole("button", { name: "Start recurring operation" });
  await expect(start).toBeDisabled();
  const consentHash = (await recurring.getByTestId("recurring-activate").locator(".mono").innerText()).trim();
  await recurring.getByRole("checkbox", { name: /I authorize repeated evaluations/ }).check();
  await start.click();
  const deployment = recurring.getByTestId("recurring-deployment");
  await expect(deployment).toHaveAttribute("data-state", "ACTIVE");
  await expect(deployment).toContainText(consentHash);
  // Activation saves no work: only a scheduler pass does, and none has run yet.
  await expect(recurring.getByTestId("recurring-wait")).toContainText("no scheduler pass was recorded");
  await expect(recurring).toContainText("No slot evaluated yet.");
  await shot(page, project, "01-activated");
  await noSeriousAxe(page);
  if (project === "mobile-390") await noSidewaysScroll(page);

  // Keyboard: the panel's controls are reachable and labelled.
  await recurring.getByRole("button", { name: "Refresh" }).focus();
  await expect(recurring.getByRole("button", { name: "Refresh" })).toBeFocused();
  record(project, { agentId, consentHash, thesisUrl });
});
