/**
 * #58 connected fixture journey through the real screens, routes, database and bounded worker.
 * Reuses the thesis revision (and its labelled synthetic replay) saved by e2e.spec.mjs in this run.
 * Fixture ports only: nothing here is a wallet, deposit, quote, transaction or chain evidence.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
const resultsFile = path.join(evidence, "ui-results.json");
const financialFile = path.join(evidence, "financial-results.json");
const TRADING = "1000000000";
const GAS = "1000000000000000000";

function record(key, value) {
  const saved = fs.existsSync(financialFile) ? JSON.parse(fs.readFileSync(financialFile, "utf8")) : {};
  saved[key] = value;
  fs.writeFileSync(financialFile, JSON.stringify(saved, null, 2));
}

async function shot(page, project, name) {
  fs.mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, `${project}-fin-${name}.png`), fullPage: true });
}

async function open(page, token) {
  await injectAuth(page, token);
  await page.goto("/");
  await expect(page.getByTestId("fixture-banner")).toContainText("TEST AUTH FIXTURE");
}

async function noSeriousAxe(page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
}

/** Wallet, funding and adopted terms for one agent, entirely through the screens. */
async function readyAgent(page, thesisUrl, agentId, project) {
  await page.goto(thesisUrl);
  const setup = page.getByRole("region", { name: "Agent wallet setup" });
  await setup.getByLabel("Agent ID").fill(agentId);
  await setup.getByRole("button", { name: "Check saved setup" }).click();
  await setup.getByRole("button", { name: "Save wallet setup" }).click();
  await setup.getByRole("button", { name: "Create wallet now" }).click();
  await expect(setup.getByTestId("wallet-setup-state")).toHaveText("Wallet confirmed");

  await setup.getByRole("link", { name: "Fund this agent" }).click();
  const funding = page.getByRole("region", { name: "Agent funding" });
  await expect(funding.getByTestId("funding-mode")).toContainText("not a wallet, a transfer or chain evidence");
  await funding.getByRole("button", { name: "Declare trading and gas assets" }).click();
  for (const [label, raw] of [["Trading capital", TRADING], ["Native MON gas", GAS]]) {
    await funding.getByLabel("Asset").selectOption({ label });
    await funding.getByLabel(/Amount in base units/).fill(raw);
    await funding.getByRole("button", { name: "Save reviewed deposit" }).click();
    await expect(funding.getByTestId("funding-flows")).toContainText(`PENDING`);
  }
  await funding.getByRole("button", { name: "Check deposits" }).click();
  await expect(funding.getByTestId("funding-credited")).toContainText("1000 credited");
  await expect(funding.getByTestId("funding-holdings")).toContainText("SYNTHETIC_FIXTURE");

  await page.goto(`/#/agents?agent=${encodeURIComponent(agentId)}`);
  const authority = page.getByRole("region", { name: "Agent authority" });
  await authority.getByRole("button", { name: "Review exact terms" }).click();
  await expect(authority.getByTestId("consent-review")).toContainText("Review hash");
  await authority.getByRole("button", { name: "Adopt these exact terms (inactive)" }).click();
  await expect(authority.getByTestId("consent-adopted")).toContainText("status INACTIVE");
  await expect(authority.getByTestId("activation-state")).toContainText("SYNTHETIC_FIXTURE_QUALIFICATION");
  await shot(page, project, `${agentId}-authority`);
}

async function runOnce(page, agentId) {
  await page.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
  const actions = page.getByRole("region", { name: "Agent actions" });
  await actions.getByRole("button", { name: "Run one bounded evaluation" }).click();
  await expect(actions.getByRole("status").filter({ hasText: "Evaluation saved" })).toBeVisible();
  return actions;
}

async function waitForJob(actions, text) {
  await expect(async () => {
    await actions.getByRole("button", { name: "Refresh" }).click();
    await expect(actions.getByTestId("actions-jobs")).toContainText(text, { timeout: 1000 });
  }).toPass({ timeout: 45_000 });
}

test.describe.configure({ mode: "serial" });

test("bounded fixture action: wallet, funding, exact terms, decision, receipt and removal", async ({ page }, info) => {
  const project = info.project.name;
  const thesis = JSON.parse(fs.readFileSync(resultsFile, "utf8"))[`thesis-${project}`];
  expect(thesis && thesis.url, "e2e.spec.mjs must save the thesis revision first").toBeTruthy();
  const agentId = `fin-${project}`;
  await open(page, tokens.a);
  await readyAgent(page, thesis.url, agentId, project);

  const actions = await runOnce(page, agentId);
  await expect(actions.getByTestId("actions-mode")).toContainText("No transaction is signed or sent");
  await waitForJob(actions, "SUBMITTED_CONFIRMED");
  await actions.getByRole("button", { name: /Open action/ }).first().click();
  const lineage = actions.getByTestId("action-lineage");
  await expect(lineage.getByTestId("action-receipts")).toHaveText("CONFIRMED");
  await expect(lineage).toContainText("FIXTURE_TRANSPORT_SIGNS_NOTHING");
  await expect(actions.getByTestId("actions-positions")).toContainText("50 base units held");
  const actionId = (await lineage.getByRole("heading", { level: 3 }).innerText()).replace("Action ", "").trim();
  await shot(page, project, "action-confirmed");
  await noSeriousAxe(page);

  // Removal: requested denies at once; the residual position and owner access stay.
  await actions.getByRole("button", { name: "Request removal" }).click();
  await expect(actions.getByTestId("actions-removal")).toContainText("Removal REQUESTED");
  await actions.getByRole("button", { name: "Check removal status" }).click();
  await expect(actions.getByTestId("actions-removal")).toContainText("Removal CONFIRMED");
  await expect(actions.getByTestId("actions-positions")).toContainText("50 base units held");
  await shot(page, project, "removal-confirmed");

  // Deep link and reload reopen the same saved state.
  await page.reload();
  const reopened = page.getByRole("region", { name: "Agent actions" });
  await expect(reopened.getByTestId("actions-jobs")).toContainText("SUBMITTED_CONFIRMED");
  await expect(reopened.getByTestId("actions-removal")).toContainText("Removal CONFIRMED");
  record(`main-${project}`, { agentId, actionId });
});

test("interrupted acknowledgement reconciles the original action, never a replacement", async ({ page }, info) => {
  const project = info.project.name;
  const thesis = JSON.parse(fs.readFileSync(resultsFile, "utf8"))[`thesis-${project}`];
  const agentId = `fin-${project}-fx-lost-ack`;
  await open(page, tokens.a);
  await readyAgent(page, thesis.url, agentId, project);
  const actions = await runOnce(page, agentId);
  await waitForJob(actions, "SUBMITTED_UNKNOWN");
  await expect(actions.getByTestId("actions-blocking")).toContainText("SUBMISSION_UNKNOWN");
  await actions.getByRole("button", { name: /Open action/ }).first().click();
  const lineage = actions.getByTestId("action-lineage");
  await expect(lineage.getByTestId("action-receipts")).toHaveText("SUBMISSION_UNKNOWN");
  await expect(lineage).not.toContainText("CONFIRMED");
  await shot(page, project, "action-unknown");
  await lineage.getByRole("button", { name: "Reconcile original action" }).click();
  await expect(lineage.getByTestId("action-receipts")).toHaveText("SUBMISSION_UNKNOWN → CONFIRMED");
  await expect(lineage.getByTestId("action-queue-state")).toHaveText("SUBMITTED_CONFIRMED");
  const actionId = (await lineage.getByRole("heading", { level: 3 }).innerText()).replace("Action ", "").trim();
  record(`lost-ack-${project}`, { agentId, actionId });
});

test("a stop denies new work before admission and a lost reply pauses new requests", async ({ page }, info) => {
  const project = info.project.name;
  const thesis = JSON.parse(fs.readFileSync(resultsFile, "utf8"))[`thesis-${project}`];
  const agentId = `fin-${project}-stop`;
  await open(page, tokens.a);
  await readyAgent(page, thesis.url, agentId, project);
  await page.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
  const actions = page.getByRole("region", { name: "Agent actions" });
  await actions.getByRole("button", { name: "Halt all swaps" }).click();
  await expect(actions.getByTestId("actions-stops")).toContainText("HALT_ALL_SWAPS");

  // A network failure on the write leaves the outcome unconfirmed: further writes pause until a read succeeds.
  await page.route("**/v1/agents/*/actions", (route) => route.request().method() === "POST" ? route.abort() : route.continue());
  await actions.getByRole("button", { name: "Run one bounded evaluation" }).click();
  await expect(actions.getByRole("alert")).toContainText("not confirmed");
  await expect(actions.getByRole("button", { name: "Run one bounded evaluation" })).toBeDisabled();
  await page.unroute("**/v1/agents/*/actions");
  await actions.getByRole("button", { name: "Check saved actions" }).click();
  await actions.getByRole("button", { name: "Run one bounded evaluation" }).click();
  await waitForJob(actions, "STOPPED_HALT_ALL_SWAPS");
  await expect(actions.getByTestId("actions-jobs")).toContainText("ADMISSION_DENIED");
  await shot(page, project, "stop-denied");
  record(`stop-${project}`, { agentId });
});

test("a requested removal denies the next evaluation before any reservation or effect", async ({ page }, info) => {
  const project = info.project.name;
  const thesis = JSON.parse(fs.readFileSync(resultsFile, "utf8"))[`thesis-${project}`];
  const agentId = `fin-${project}-removed`;
  await open(page, tokens.a);
  await readyAgent(page, thesis.url, agentId, project);
  await page.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
  const actions = page.getByRole("region", { name: "Agent actions" });
  await actions.getByRole("button", { name: "Request removal" }).click();
  await expect(actions.getByTestId("actions-removal")).toContainText("Removal REQUESTED");
  await actions.getByRole("button", { name: "Run one bounded evaluation" }).click();
  await waitForJob(actions, "REMOVAL_REQUESTED");
  await expect(actions.getByTestId("actions-jobs")).toContainText("ADMISSION_DENIED");
  await shot(page, project, "removal-denied");
  record(`removed-${project}`, { agentId });
});

test("another owner sees none of these agents or actions", async ({ page }, info) => {
  const project = info.project.name;
  const saved = JSON.parse(fs.readFileSync(financialFile, "utf8"))[`main-${project}`];
  await open(page, tokens.b);
  for (const area of ["funds", "agents", "positions"]) {
    await page.goto(`/#/${area}?agent=${encodeURIComponent(saved.agentId)}`);
    await expect(page.getByText(/No confirmed wallet|no confirmed wallet|AGENT_NOT_READY|confirmed wallet bound/).first()).toBeVisible();
  }
  await expect(page.getByText(saved.actionId)).toHaveCount(0);
});
