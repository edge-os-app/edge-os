/**
 * P31 LOCAL agent health (lane 3). Driven only by scripts/p03/agent_health_runtime_run.py on its own isolated
 * instance; it is not part of the shared mapped verifier. Each browser width is its own owner with one recurring
 * deployment that separate producer processes advanced while no browser was open. The page's direct health panel and
 * the read-only conversation must quote the same dated snapshot as the API, keep unknowns explicit, never offer a
 * financial control and survive an API restart in a new browser context. Authored fixture ports only.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
const resultsFile = path.join(evidence, "agent-health-results.json");
const api = process.env.P03_API_URL;
const tokenFor = (project) => process.env[`P31_TOKEN_${project.replace("-", "_").toUpperCase()}`];
const agentFor = (project) => process.env[`P31_AGENT_${project.replace("-", "_").toUpperCase()}`];

function saved() { return fs.existsSync(resultsFile) ? JSON.parse(fs.readFileSync(resultsFile, "utf8")) : {}; }
function record(key, value) {
  const all = saved();
  all[key] = { ...(all[key] ?? {}), ...value };
  fs.writeFileSync(resultsFile, JSON.stringify(all, null, 2));
}

async function shot(page, project, name) {
  fs.mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, `${project}-health-${name}.png`), fullPage: true });
}

async function apiHealth(request, token, agentId) {
  const response = await request.get(`${api}/v1/agents/${encodeURIComponent(agentId)}/health`,
    { headers: { Authorization: `Bearer ${token}` } });
  expect(response.status()).toBe(200);
  return response.json();
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

/** The conversation surface for this width: the side panel on desktop, the sheet at 390px. */
async function conversation(page, project) {
  if (project === "mobile-390") {
    await page.getByRole("button", { name: "Conversation" }).click();
    return page.getByRole("dialog", { name: "Conversation" });
  }
  return page.getByRole("complementary", { name: "Conversation" });
}

const asOfText = (asOf) => (asOf ? `${asOf.time} (${asOf.table} ${asOf.id} ${asOf.field})` : "No stored write");

async function directAndConversationAgree(page, project, request, token, agentId) {
  const health = await apiHealth(request, token, agentId);
  await page.goto(`/#/agents?agent=${encodeURIComponent(agentId)}`);
  const panel = page.getByRole("region", { name: "Agent health" });
  await expect(panel.getByTestId("health-digest")).toHaveText(health.snapshot_digest);
  await expect(panel.getByTestId("health-as-of")).toHaveText(asOfText(health.as_of));
  const next = health.producer.next_due_slot;
  await expect(panel.getByTestId("health-next")).toHaveText(next.state === "KNOWN" ? String(next.value) : `Unknown (${next.reason})`);
  await expect(panel.getByTestId("health-unknowns")).toContainText("native_gas_aggregate");
  const convo = await conversation(page, project);
  const replies = convo.getByTestId("health-reply");
  const count = await replies.count();
  await convo.getByRole("button", { name: "What did it last do?" }).click();
  await expect(replies).toHaveCount(count + 1);
  const reply = replies.last();
  await expect(reply).toHaveAttribute("data-digest", health.snapshot_digest);
  await expect(reply).toContainText(`Stored as of ${asOfText(health.as_of)}`);
  return { health, panel, convo, reply };
}

test("health stage A: direct view and conversation quote one dated snapshot", async ({ page, request }, info) => {
  const project = info.project.name;
  const token = tokenFor(project);
  const agentId = agentFor(project);
  expect(token && agentId, "the runner mints one owner and agent per width").toBeTruthy();
  await injectAuth(page, token);
  const { health, panel, convo, reply } = await directAndConversationAgree(page, project, request, token, agentId);
  if (project === "desktop") {
    // Slot 0 traded and slot 5 exited after the owner stopped new entries.
    await expect(panel.getByTestId("health-controls")).toContainText("STOP_NEW_ENTRIES");
    await expect(panel.getByTestId("health-wait")).toContainText("STOPPED:STOP_NEW_ENTRIES");
    await expect(reply).toContainText("Last trade attempt: action");
  } else {
    // The original action's acknowledgement was lost: it is the canonical pending item; warnings stay separate.
    const pending = health.pending_reconciliation.canonical.action_ids;
    expect(pending.length).toBe(1);
    await expect(panel.getByTestId("health-pending")).toContainText(pending[0]);
    await expect(panel.getByTestId("health-wait")).toContainText("WAITING_RECONCILIATION");
    await convo.getByRole("button", { name: "Is anything pending?" }).click();
    await expect(convo.getByTestId("health-reply")).toHaveCount(2);
    await expect(convo.getByTestId("health-reply").last()).toContainText("Pending reconciliation (producer unsettled queue): " + pending[0]);
  }
  await convo.getByLabel("Ask about this agent's health").fill("What is unknown about gas?");
  const asked = await convo.getByTestId("health-reply").count();
  await convo.getByRole("button", { name: "Ask" }).click();
  await expect(convo.getByTestId("health-reply")).toHaveCount(asked + 1);
  await expect(convo.getByTestId("health-reply").last()).toContainText("native_gas_aggregate: UNKNOWN");
  // A read-only conversation: only questions and Ask, never a financial control.
  const names = await convo.getByRole("button").allInnerTexts();
  expect(names.filter((name) => !["Close", "Ask"].includes(name.trim()) && !name.trim().endsWith("?"))).toEqual([]);
  await shot(page, project, "01-direct-and-conversation");
  await noSeriousAxe(page);
  if (project === "mobile-390") await noSidewaysScroll(page);
  // Keyboard: the question field is reachable and labelled.
  await convo.getByLabel("Ask about this agent's health").focus();
  await expect(convo.getByLabel("Ask about this agent's health")).toBeFocused();
  record(project, { agentId, record_id: health.record_id, snapshot_digest: health.snapshot_digest, as_of: health.as_of,
    deployment: health.deployment, unknown_inputs: health.unknown_inputs.map((u) => u.field),
    pending: health.pending_reconciliation.canonical.action_ids ?? null, read_at: health.read_at });
});

test("health intruder: another owner cannot read or retarget either agent", async ({ page, request }, info) => {
  const project = info.project.name;
  const intruder = process.env.P31_TOKEN_INTRUDER;
  const agentId = agentFor(project);
  for (const suffix of ["/health", "/health/explanation?question=what%20did%20it%20do"]) {
    const response = await request.get(`${api}/v1/agents/${encodeURIComponent(agentId)}${suffix}`,
      { headers: { Authorization: `Bearer ${intruder}` } });
    expect(response.status()).toBe(404);
  }
  await injectAuth(page, intruder);
  await page.goto(`/#/agents?agent=${encodeURIComponent(agentId)}`);
  await expect(page.getByRole("region", { name: "Agent health" }).getByRole("alert")).toBeVisible();
  const convo = await conversation(page, project);
  await convo.getByRole("button", { name: "What did it last do?" }).click();
  await expect(convo.getByRole("alert")).toBeVisible();
  await expect(convo.getByTestId("health-reply")).toHaveCount(0);
  await shot(page, project, "02-intruder");
  record(`intruder-${project}`, { agentId, refused: true });
});

test("health after restart: a new browser context reads the same snapshot identity", async ({ page, request }, info) => {
  const project = info.project.name;
  const token = tokenFor(project);
  const before = saved()[project];
  expect(before, "stage A saved its snapshot").toBeTruthy();
  await injectAuth(page, token);
  const { health } = await directAndConversationAgree(page, project, request, token, before.agentId);
  expect(health.record_id).toBe(before.record_id);
  expect(health.snapshot_digest).toBe(before.snapshot_digest);
  expect(health.as_of).toEqual(before.as_of);
  expect(health.unknown_inputs.map((u) => u.field)).toEqual(before.unknown_inputs);
  await shot(page, project, "03-after-restart");
  record(`restart-${project}`, { record_id: health.record_id, snapshot_digest: health.snapshot_digest, read_at: health.read_at });
});
