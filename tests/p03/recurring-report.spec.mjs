/**
 * #58 P27 LOCAL, later phases. scripts/p03/recurring_phase.py runs producer processes between these stages and
 * selects each stage with --grep; every stage opens a new browser context, so nothing carries over from a page.
 *
 * - "stage A": after passes at slots 0, 5, 10 and 25 (15 and 20 missed). The desktop owner traded entry, full exit,
 *   re-entry and exit; the 390px owner's unknown actions were reconciled one by one. Desktop stops new entries; the
 *   390px owner ends recurring operation while its latest action is still unknown.
 * - "stage B": after the pass at slot 30. The desktop entry was denied by the stop and desktop requests removal; the
 *   390px deployment produced nothing new, and its unknown action was reconciled after the end.
 * - "stage C": after the pass at slot 35. Both deployments ended; residual holdings and reads remain.
 * - "after restart": the same durable record reopens after the API restart and one more producer pass.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth } from "./fixture-auth.mjs";

const ownerToken = (project) => process.env[`P03_TOKEN_REC_${project.replace("-", "_").toUpperCase()}`];
const agentFor = (project) => (project === "desktop" ? "rec-desktop" : "rec-mobile-390-fx-lost-ack");

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
const resultsFile = path.join(evidence, "recurring-results.json");
const api = process.env.P03_API_URL;
const other = (project) => (project === "desktop" ? "mobile-390" : "desktop");

function saved(project) {
  return JSON.parse(fs.readFileSync(resultsFile, "utf8"))[project];
}

function record(key, value) {
  const all = fs.existsSync(resultsFile) ? JSON.parse(fs.readFileSync(resultsFile, "utf8")) : {};
  all[key] = { ...(all[key] ?? {}), ...value };
  fs.writeFileSync(resultsFile, JSON.stringify(all, null, 2));
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

async function openRecurring(page, project) {
  const agentId = agentFor(project);
  await injectAuth(page, ownerToken(project));
  await page.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
  const recurring = page.getByRole("region", { name: "Recurring operation" });
  await expect(recurring.getByTestId("recurring-deployment")).toBeVisible();
  return { agentId, recurring, actions: page.getByRole("region", { name: "Agent actions" }) };
}

async function projection(page, project) {
  const response = await page.request.get(`${api}/v1/agents/${encodeURIComponent(agentFor(project))}/deployment`,
    { headers: { Authorization: `Bearer ${ownerToken(project)}` } });
  expect(response.status()).toBe(200);
  return response.json();
}

test("stage A: repeated slots ran while the browser was closed", async ({ page }, info) => {
  const project = info.project.name;
  const { agentId, recurring, actions } = await openRecurring(page, project);
  const view = await projection(page, project);
  // Slots 15 and 20, plus any slot between activation and the first pass (counted from the activation slot).
  expect(view.producer.missed_slots).toBeGreaterThanOrEqual(2);
  expect(view.producer.missed_intervals.every((item) => item.reason === "PRODUCER_ABSENT")).toBe(true);
  await expect(recurring.getByTestId("recurring-missed")).toContainText("not replayed");
  const items = recurring.getByTestId("recurring-occurrences").locator("li");
  await expect(items).toHaveCount(4);
  await expect(recurring.getByTestId("recurring-occurrences")).toContainText("SYNTHETIC_FIXTURE");
  if (project === "desktop") {
    expect(view.occurrences.map((item) => item.outcome)).toEqual(Array(4).fill("SUBMITTED_CONFIRMED"));
    await expect(recurring.getByTestId("recurring-wait")).toContainText("Active. Next slot");
    await expect(recurring.getByTestId("recurring-pending")).toHaveText("None");
    await expect(actions.getByTestId("actions-positions")).toContainText("0 base units held");
    // The owner stops new entries while recurring operation continues; existing exits stay allowed.
    await actions.getByRole("button", { name: "Stop new entries" }).click();
    await expect(actions.getByRole("status").filter({ hasText: "New entries are stopped." })).toBeVisible();
  } else {
    // Every earlier unknown action was reconciled from its receipt before the next one could trade.
    expect(view.occurrences.slice(1).every((item) => item.outcome === "SUBMITTED_CONFIRMED")).toBe(true);
    expect(view.occurrences[0].outcome).toBe("SUBMITTED_UNKNOWN");
    await expect(recurring.getByTestId("recurring-wait")).toContainText("an earlier action's outcome is unknown");
    await expect(recurring.getByTestId("recurring-pending")).toHaveText(view.occurrences[0].action_id);
    // The owner ends recurring operation while that action is still unknown; its receipt is read later anyway.
    await recurring.getByRole("button", { name: "End recurring operation" }).click();
    await expect(recurring.getByTestId("recurring-wait")).toContainText("Ended: You ended recurring operation.");
    await expect(recurring.getByTestId("recurring-pending")).toHaveText(view.occurrences[0].action_id);
  }
  // Another owner sees no deployment of this agent.
  const foreign = await page.request.get(`${api}/v1/agents/${encodeURIComponent(agentId)}/deployment`,
    { headers: { Authorization: `Bearer ${ownerToken(other(project))}` } });
  expect(foreign.status()).toBe(404);
  await shot(page, project, "02-after-passes");
  await noSeriousAxe(page);
  if (project === "mobile-390") await noSidewaysScroll(page);
  record(project, { stageA: view });
});

test("stage B: the stop denied the next entry; removal; the ended deployment's unknown action reconciled", async ({ page }, info) => {
  const project = info.project.name;
  const { recurring, actions } = await openRecurring(page, project);
  const view = await projection(page, project);
  if (project === "desktop") {
    expect(view.occurrences[0].outcome).toBe("ADMISSION_DENIED");
    expect(view.occurrences[0].reason).toBe("STOPPED_NEW_ENTRIES");
    await expect(recurring.getByTestId("recurring-wait")).toContainText("Stopped: stop new entries");
    await actions.getByRole("button", { name: "Request removal" }).click();
    await expect(actions.getByTestId("actions-removal")).toContainText("Removal REQUESTED");
  } else {
    // The pass at slot 30 created no occurrence for the ended deployment and still reconciled its unknown action.
    const before = saved(project).stageA;
    expect(view.deployment.state).toBe("ENDED");
    expect(view.occurrences.map((item) => item.job_id)).toEqual(before.occurrences.map((item) => item.job_id));
    expect(view.occurrences.every((item) => item.outcome === "SUBMITTED_CONFIRMED")).toBe(true);
    expect(view.pending_reconciliation).toEqual([]);
    await expect(recurring.getByTestId("recurring-pending")).toHaveText("None");
    await expect(recurring.getByTestId("recurring-next")).toContainText("None (OWNER_ENDED)");
  }
  await shot(page, project, "03-controls");
  if (project === "mobile-390") await noSidewaysScroll(page);
  record(project, { stageB: view });
});

test("stage C: both deployments ended; holdings and reads remain", async ({ page }, info) => {
  const project = info.project.name;
  const { recurring, actions } = await openRecurring(page, project);
  const view = await projection(page, project);
  const before = saved(project).stageB;
  expect(view.deployment.state).toBe("ENDED");
  if (project === "desktop") {
    expect(view.deployment.end_reason).toBe("REMOVAL_REQUESTED");
    expect(view.occurrences.length).toBe(before.occurrences.length);  // no occurrence after the removal
    await expect(recurring.getByTestId("recurring-wait")).toContainText("Ended: Agent removal was requested.");
  } else {
    expect(view.deployment.end_reason).toBe("OWNER_ENDED");
    expect(view.occurrences.length).toBe(4);  // no occurrence after the end
    expect(view.pending_reconciliation).toEqual([]);
  }
  await expect(actions.getByTestId("actions-positions")).toBeVisible();  // residual holdings stay readable
  await shot(page, project, "04-ended");
  await noSeriousAxe(page);
  if (project === "mobile-390") await noSidewaysScroll(page);
  record(project, { stageC: view });
});

test("after restart: the durable record reopens unchanged", async ({ page }, info) => {
  const project = info.project.name;
  const { recurring } = await openRecurring(page, project);
  const view = await projection(page, project);
  const before = saved(project).stageC;
  expect(view.deployment).toEqual(before.deployment);
  expect(view.producer.cursor_slot).toBe(before.producer.cursor_slot);
  expect(view.occurrences.map((item) => [item.job_id, item.outcome, item.action_id]))
    .toEqual(before.occurrences.map((item) => [item.job_id, item.outcome, item.action_id]));
  await expect(recurring.getByTestId("recurring-deployment")).toHaveAttribute("data-state", "ENDED");
  await shot(page, project, "05-reopened");
});
