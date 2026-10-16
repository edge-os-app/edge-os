/**
 * LOCAL Docker rehearsal: reopen the seeded records through the packaged web and API, using GET requests only.
 * Runs after process replacement and again on the restored stack. Each test fails on any non-GET /v1 request, so a
 * reopen can neither recompute nor replace a saved result. TEST AUTH FIXTURE owners and synthetic records only.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

const ui = process.env.P03_EVIDENCE_DIR;
const out = process.env.REHEARSAL_EVIDENCE_DIR ?? ".evidence";
const stage = process.env.REHEARSAL_STAGE ?? "stage";
const api = process.env.P03_API_URL;
const tokens = { a: process.env.P03_TOKEN_A, b: process.env.P03_TOKEN_B };
const seeded = JSON.parse(fs.readFileSync(process.env.REHEARSAL_EXPECTED, "utf8")).named;
const research = JSON.parse(fs.readFileSync(path.join(ui, "research-results.json"), "utf8"));
const recurring = JSON.parse(fs.readFileSync(path.join(ui, "recurring-results.json"), "utf8"));

function record(project, key, value) {
  const file = path.join(out, `reopen-${project}.json`);
  const saved = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : { stage };
  saved[key] = value;
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(file, JSON.stringify(saved, null, 2));
}

async function shot(page, project, name) {
  fs.mkdirSync(path.join(out, "screenshots"), { recursive: true });
  await page.screenshot({ path: path.join(out, "screenshots", `${stage}-${project}-${name}.png`), fullPage: true });
}

/** Every request to /v1 that is not a read, every console error and every failed response. Writes must stay empty. */
function watchWrites(page) {
  const writes = [];
  const problems = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/v1") && !["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      writes.push(`${request.method()} ${url.pathname}`);
    }
  });
  page.on("console", (message) => { if (message.type() === "error") problems.push(`console: ${message.text().slice(0, 160)}`); });
  page.on("response", (response) => {
    if (response.status() >= 400) problems.push(`${response.status()} ${new URL(response.url()).pathname}`);
  });
  page.on("requestfailed", (request) => problems.push(`failed ${new URL(request.url()).pathname}`));
  return { writes, problems };
}

async function open(page, token) {
  await page.addInitScript((value) => {
    window.__EDGE_OS_TEST_AUTH__ = { label: "TEST AUTH FIXTURE · not Privy · LOCAL Docker rehearsal",
      getAccessToken: async () => value, signOut() {} };
  }, token);
  await page.goto("/");
  await expect(page.getByTestId("fixture-banner")).toContainText("TEST AUTH FIXTURE");
}

async function checkLayout(page, project) {
  if (project === "mobile-390") {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, "no sideways scroll at 390px").toBeLessThanOrEqual(0);
  }
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
}

/** Tab through the first controls: each focused element is visible and has an accessible name. */
async function checkKeyboard(page) {
  const seen = [];
  for (let step = 0; step < 6; step += 1) {
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const box = el.getBoundingClientRect();
      const labelled = el.getAttribute("aria-label") || (el.id && document.querySelector(`label[for="${el.id}"]`)?.textContent)
        || el.closest("label")?.textContent || el.textContent || el.getAttribute("title") || el.getAttribute("value") || "";
      return { tag: el.tagName.toLowerCase(), name: labelled.trim().slice(0, 60), visible: box.width > 0 && box.height > 0 };
    });
    if (focused) seen.push(focused);
  }
  expect(seen.length, "keyboard focus reaches page controls").toBeGreaterThan(0);
  for (const item of seen) {
    expect(item.visible, `${item.tag} is visible when focused`).toBe(true);
    expect(item.name, `${item.tag} has an accessible name`).not.toBe("");
  }
  return seen;
}

test("saved report, jobs, held unknown and usage reopen without recomputation", async ({ page }, info) => {
  const project = info.project.name;
  const run = research[`research-${project}`];
  const { writes, problems } = watchWrites(page);
  await open(page, tokens.a);
  await page.goto(run.url);
  const section = page.getByTestId("history-investigation");
  await expect(section).toBeVisible();
  await expect(section.getByTestId("research-budget")).toContainText("provider requests");
  await section.locator(".card").filter({ hasText: run.hypothesis }).getByRole("button", { name: "Open this declaration" }).click();
  await expect(section.getByTestId("history-declaration")).toBeVisible();
  const cards = section.getByTestId("history-job");
  await expect(cards).toHaveCount(5);
  const states = await cards.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-state")));
  expect(states).toEqual(["REPORTED", "CANCELLED", "REPORTED", "UNAVAILABLE", "REPORTED"]);
  await expect(cards.nth(0).getByTestId("history-report-id")).toHaveText(run.reportId);
  await expect(cards.nth(3)).toContainText("not collected again");
  expect(seeded.reports.map((row) => row[0])).toContain(run.reportId);
  const job = await page.request.get(`${api}/v1/research/requests/${run.intakeId}/history-investigations/${run.main}/jobs`,
    { headers: { Authorization: `Bearer ${tokens.a}` } });
  expect(job.status()).toBe(200);
  const jobs = (await job.json()).jobs;
  expect(jobs.map((item) => item.job_id)).toEqual(expect.arrayContaining(Object.values(run.jobs).filter((id) => id !== run.jobs.failing)));
  expect(jobs[3].budget.unknown_liability.provider_requests).toBe(2);
  expect(seeded.held_unknown.map((row) => row[0])).toContain(run.jobs.killed);
  await shot(page, project, "report-and-jobs");
  await checkLayout(page, project);
  record(project, "research", { reportId: run.reportId, states, killedJob: run.jobs.killed });
  expect(writes, "reopen sends reads only").toEqual([]);
  expect(problems, "no console error or failed response").toEqual([]);
});

test("saved revision and labelled replay reopen as the exact saved result", async ({ page }, info) => {
  const project = info.project.name;
  const run = research[`research-${project}`];
  const { writes, problems } = watchWrites(page);
  await open(page, tokens.a);
  await page.goto(run.strategyUrl);
  await expect(page.getByTestId("revision-id")).toHaveText(run.historyRevision);
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  expect(seeded.revisions.map((row) => row[0])).toContain(run.historyRevision);
  const replay = page.getByTestId("spot-replay");
  await replay.getByLabel("Saved replay ID").fill(run.replayId);
  await replay.getByRole("button", { name: "Load saved replay" }).click();
  await expect(replay.getByTestId("spot-replay-id")).toHaveText(run.replayId);
  await expect(replay).toContainText("Loaded the exact saved result. The replay did not run again.");
  expect(seeded.replays.map((row) => row[0])).toContain(run.replayId);
  await shot(page, project, "revision-and-replay");
  await checkLayout(page, project);
  record(project, "strategy", { revisionId: run.historyRevision, replayId: run.replayId });
  expect(writes, "reopen sends reads only").toEqual([]);
  expect(problems, "no console error or failed response").toEqual([]);
});

test("recurring deployment reopens with its saved state and consent", async ({ page }, info) => {
  const project = info.project.name;
  const saved = recurring[project];
  const owner = project === "desktop" ? tokens.a : tokens.b;
  const deployment = seeded.deployments.find((row) => row[1] === saved.agentId);
  expect(deployment, "the seeded snapshot holds this owner's deployment").toBeTruthy();
  const { writes, problems } = watchWrites(page);
  await open(page, owner);
  await page.goto(`/#/positions?agent=${encodeURIComponent(saved.agentId)}`);
  const panel = page.getByRole("region", { name: "Recurring operation" });
  const shown = panel.getByTestId("recurring-deployment");
  await expect(shown).toHaveAttribute("data-state", deployment[2]);
  await expect(shown).toContainText(saved.consentHash);
  expect(deployment[3]).toBe(saved.consentHash);
  await shot(page, project, "recurring-deployment");
  await checkLayout(page, project);
  const focus = await checkKeyboard(page);
  record(project, "recurring", { agentId: saved.agentId, deploymentId: deployment[0], state: deployment[2], focus });
  expect(writes, "reopen sends reads only").toEqual([]);
  expect(problems, "no console error or failed response").toEqual([]);
});

test("another owner gets a refusal, not the saved records", async ({ page }, info) => {
  const project = info.project.name;
  const run = research[`research-${project}`];
  const { writes, problems } = watchWrites(page);
  const direct = await page.request.get(`${api}/v1/research/requests/${run.intakeId}`, { headers: { Authorization: `Bearer ${tokens.b}` } });
  expect(direct.status()).toBe(404);
  await open(page, tokens.b);
  await page.goto(run.url);
  await expect(page.getByRole("alert").filter({ hasText: "This request was not found." })).toBeVisible();
  await expect(page.getByTestId("history-investigation")).toHaveCount(0);
  await expect(page.getByText(run.hypothesis)).toHaveCount(0);
  await expect(page.getByText(run.reportId)).toHaveCount(0);
  await shot(page, project, "other-owner-refused");
  await checkLayout(page, project);
  // The refusal itself is a 404; nothing else may fail.
  const unexpected = problems.filter((item) => !/^404 \/v1\//.test(item) && !/^console: Failed to load resource.*404/.test(item));
  record(project, "other_owner", { status: direct.status(), refusals: problems });
  expect(unexpected, "only the expected 404 refusals").toEqual([]);
  expect(writes, "reopen sends reads only").toEqual([]);
});
