/**
 * #58 ORIGINAL-LOCAL: the original transaction through the real screens, routes, database and bounded worker.
 * The `fx-original` agents use AUTHORED recorded responses (route quote, signer reply, chain reads) replayed by
 * offline clients; nothing here signs with a real key, sends a transaction or reads a chain.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";
import { apiGet, apiPost } from "./research-flow.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
const resultsFile = path.join(evidence, "ui-results.json");
const financialFile = path.join(evidence, "financial-results.json");

function record(key, value) {
  const saved = fs.existsSync(financialFile) ? JSON.parse(fs.readFileSync(financialFile, "utf8")) : {};
  saved[key] = value;
  fs.writeFileSync(financialFile, JSON.stringify(saved, null, 2));
}

async function shot(page, project, name) {
  fs.mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, `${project}-orig-${name}.png`), fullPage: true });
}

async function noSidewaysScroll(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function noSeriousAxe(page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
}

/** Wallet on Monad mainnet (143), funding and adopted terms, entirely through the screens and the keyboard. */
async function readyOriginalAgent(page, thesisUrl, agentId, project) {
  await page.goto(thesisUrl);
  const setup = page.getByRole("region", { name: "Agent wallet setup" });
  await setup.getByLabel("Agent ID").fill(agentId);
  await setup.getByRole("button", { name: "Check saved setup" }).click();
  await setup.getByLabel("Requested network").selectOption({ label: "Monad mainnet (143)" });
  await setup.getByRole("button", { name: "Save wallet setup" }).click();
  await setup.getByRole("button", { name: "Create wallet now" }).focus();
  await page.keyboard.press("Enter");
  await expect(setup.getByTestId("wallet-setup-state")).toHaveText("Wallet confirmed");

  await setup.getByRole("link", { name: "Fund this agent" }).click();
  const funding = page.getByRole("region", { name: "Agent funding" });
  await funding.getByRole("button", { name: "Declare trading and gas assets" }).click();
  for (const [label, raw] of [["Trading capital", "1000000000"], ["Native MON gas", "1000000000000000000"]]) {
    await funding.getByLabel("Asset").selectOption({ label });
    await funding.getByLabel(/Amount in base units/).fill(raw);
    await funding.getByRole("button", { name: "Save reviewed deposit" }).click();
    await expect(funding.getByTestId("funding-flows")).toContainText("PENDING");
  }
  await funding.getByRole("button", { name: "Check deposits" }).click();
  await expect(funding.getByTestId("funding-credited")).toContainText("1000 credited");
  // Current holdings are the recorded observation of the bound wallet, apart from the deposit history.
  await expect(funding.getByTestId("funding-holdings-observation")).toContainText("(FINALIZED) for 0x2c7536E3605D9C16a7a3D7b1898e529396a65c23 · recorded-holdings/1");
  await expect(funding.getByTestId("funding-holdings")).toContainText("AUTHORED_RECORDING");
  await shot(page, project, `${agentId}-holdings`);
  await noSidewaysScroll(page);

  await page.goto(`/#/agents?agent=${encodeURIComponent(agentId)}`);
  const authority = page.getByRole("region", { name: "Agent authority" });
  await authority.getByRole("button", { name: "Review exact terms" }).click();
  await expect(authority.getByTestId("consent-review")).toContainText("Review hash");
  await authority.getByRole("button", { name: "Adopt these exact terms (inactive)" }).click();
  await expect(authority.getByTestId("consent-adopted")).toContainText("status INACTIVE");
}

async function runAndWait(page, agentId, text) {
  await page.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
  const actions = page.getByRole("region", { name: "Agent actions" });
  await actions.getByRole("button", { name: "Run one bounded evaluation" }).click();
  await expect(actions.getByRole("status").filter({ hasText: "Evaluation saved" })).toBeVisible();
  await expect(async () => {
    await actions.getByRole("button", { name: "Refresh" }).click();
    await expect(actions.getByTestId("actions-jobs")).toContainText(text, { timeout: 1000 });
  }).toPass({ timeout: 45_000 });
  return actions;
}

test.describe.configure({ mode: "serial" });

test("the original transaction is saved, sent once, shown as unknown, then reconciled from its own receipt", async ({ page }, info) => {
  const project = info.project.name;
  const thesis = JSON.parse(fs.readFileSync(resultsFile, "utf8"))[`thesis-${project}`];
  expect(thesis && thesis.url, "e2e.spec.mjs must save the thesis revision first").toBeTruthy();
  const agentId = `orig-${project}-fx-original`;
  await injectAuth(page, tokens.a);
  await readyOriginalAgent(page, thesis.url, agentId, project);

  const actions = await runAndWait(page, agentId, "SUBMITTED_UNKNOWN");
  await actions.getByRole("button", { name: /Open action/ }).first().click();
  const lineage = actions.getByTestId("action-lineage");
  const original = lineage.getByTestId("action-original");
  await expect(original.getByTestId("action-original-stage")).toContainText("Its effect is unknown until its own receipt is reconciled");
  await expect(original.getByTestId("action-original-hash")).toHaveText(/^0x[0-9a-f]{64}$/);
  await expect(original).toContainText("not a live provider or chain");
  await expect(lineage.getByTestId("action-receipts")).toHaveText("SUBMISSION_UNKNOWN");
  const transactionHash = await original.getByTestId("action-original-hash").innerText();
  const actionId = (await lineage.getByRole("heading", { level: 3 }).innerText()).replace("Action ", "").trim();
  await shot(page, project, "unknown");
  await noSeriousAxe(page);
  await noSidewaysScroll(page);

  await lineage.getByRole("button", { name: "Reconcile original action" }).click();
  await expect(lineage.getByTestId("action-receipts")).toHaveText("SUBMISSION_UNKNOWN → CONFIRMED");
  await expect(lineage.getByTestId("action-queue-state")).toHaveText("SUBMITTED_CONFIRMED");
  await expect(original.getByTestId("action-original-hash")).toHaveText(transactionHash);
  await shot(page, project, "confirmed");

  // A deep link and a reload reopen the same saved original.
  await page.reload();
  const reopened = page.getByRole("region", { name: "Agent actions" });
  await expect(reopened.getByTestId("actions-jobs")).toContainText("SUBMITTED_CONFIRMED");
  record(`original-${project}`, { agentId, actionId, transactionHash });
});

test("a lost signer reply keeps the reserved amounts and is never sent or replaced", async ({ page }, info) => {
  const project = info.project.name;
  const thesis = JSON.parse(fs.readFileSync(resultsFile, "utf8"))[`thesis-${project}`];
  const agentId = `orig-${project}-fx-original-fx-lost-sign`;
  await injectAuth(page, tokens.a);
  await readyOriginalAgent(page, thesis.url, agentId, project);
  const actions = await runAndWait(page, agentId, "SUBMITTED_UNKNOWN");
  await actions.getByRole("button", { name: /Open action/ }).first().click();
  const lineage = actions.getByTestId("action-lineage");
  await expect(lineage.getByTestId("action-original-stage")).toContainText("The signer reply was lost");
  await expect(lineage.getByTestId("action-original-hash")).toHaveText("None saved");
  await lineage.getByRole("button", { name: "Reconcile original action" }).click();
  await expect(lineage.getByTestId("action-queue-state")).toHaveText("SUBMITTED_UNKNOWN");
  await expect(lineage.getByTestId("action-receipts")).not.toContainText("CONFIRMED");
  await expect(lineage).toContainText("RESERVED");
  const actionId = (await lineage.getByRole("heading", { level: 3 }).innerText()).replace("Action ", "").trim();
  await shot(page, project, "lost-sign");
  await noSidewaysScroll(page);
  record(`original-lost-${project}`, { agentId, actionId });
});

test("another owner cannot open the original action", async ({ page }, info) => {
  const saved = JSON.parse(fs.readFileSync(financialFile, "utf8"))[`original-${info.project.name}`];
  expect((await apiGet(page, tokens.b, `/v1/actions/${saved.actionId}`)).status).toBe(404);
  expect((await apiPost(page, tokens.b, `/v1/actions/${saved.actionId}/reconcile`, {})).status).toBe(404);
});
