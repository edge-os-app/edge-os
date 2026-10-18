/**
 * P05 browser checks: the Research path with the ACTUAL pinned Hermes against a LOCAL FAKE provider.
 *
 * The API under test was started by `scripts/hermes_interpretation/serve_local.py`. Its provider answers from a script
 * queue that this spec fills before each action, so every state below is authored, not generated. Nothing here shows how a
 * real model reads a request. Evidence: `p05-results.json` and `quality/p05-*`, `screenshots/*-p05-*`.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
const quality = path.join(evidence, "quality");
fs.mkdirSync(shots, { recursive: true });
fs.mkdirSync(quality, { recursive: true });
const resultsFile = path.join(evidence, "p05-results.json");
const queueFile = process.env.P05_SCRIPT_FILE;

const THESIS = "Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. Spot only.";
const HUNCH = "Recent rises seem to keep running. Is that worth testing?";
const LAUNCH_AGE = "Tokens launched in the last 24 hours seem to keep running after a rise. Is that worth testing?";
const REPLY_BOTH = "Enter when price is up more than 2% over the last 15 minutes, and exit when the last 5 minute return is below zero";
const REPLY_TWO = "Price up more than 1% over the last 15 minutes. Actually, price up more than 2% over the last 15 minutes";
const REPLY_OVERWRITE = "Exit when the return is below zero, and make the entry more than 2%";
const MIN = 44;

function record(key, value) {
  const current = fs.existsSync(resultsFile) ? JSON.parse(fs.readFileSync(resultsFile, "utf8")) : {};
  current[key] = value;
  fs.writeFileSync(resultsFile, JSON.stringify(current, null, 2));
}

/** Queue the provider behaviour for the next turns. The API process consumes one item per Hermes turn. */
function script(...items) {
  const current = JSON.parse(fs.readFileSync(queueFile, "utf8"));
  fs.writeFileSync(queueFile, JSON.stringify([...current, ...items]));
}
const remaining = () => JSON.parse(fs.readFileSync(queueFile, "utf8")).length;

async function shot(page, project, name) {
  await page.screenshot({ path: path.join(shots, `${project}-p05-${name}.png`), fullPage: true });
}

async function open(page, token) {
  await injectAuth(page, token);
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
}

/** Type a request and submit it with the keyboard. Returns the saved request id from the address. */
async function submit(page, text, kind = /Specific rule or thesis/) {
  await page.getByLabel("Your words", { exact: true }).fill(text);
  await page.getByRole("radio", { name: kind }).check();
  await page.getByRole("button", { name: "Prepare request" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("outcome")).toBeVisible({ timeout: 90_000 });
  return page.url().split("/research/")[1];
}

async function smallControls(page) {
  return page.evaluate((min) => {
    const small = [];
    for (const el of document.querySelectorAll('button, a[href], summary, textarea, input:not([type="hidden"])')) {
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      const box = (el.matches('input[type="radio"], input[type="checkbox"]') ? el.closest("label") ?? el : el).getBoundingClientRect();
      if (box.width === 0 || box.height === 0 || box.right < 0 || box.bottom < 0) continue;
      if (box.height < min - 0.5) small.push({ tag: el.tagName, label: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 50), height: Math.round(box.height) });
    }
    return small;
  }, MIN);
}

/** Quality of the current state: control size, sideways scroll, and axe WCAG 2.2 AA (serious and critical must be empty). */
async function inspect(page, project, name) {
  const small = await smallControls(page);
  const overflow = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }));
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  const blocking = axe.violations.filter((v) => ["serious", "critical"].includes(v.impact)).map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length }));
  const result = { small, overflow, axe_blocking: blocking, axe_all: axe.violations.map((v) => v.id) };
  fs.writeFileSync(path.join(quality, `p05-${project}-${name}.json`), JSON.stringify(result, null, 2));
  expect(small, `controls under ${MIN}px in ${name}`).toEqual([]);
  expect(overflow.scrollWidth, `sideways scroll in ${name}`).toBeLessThanOrEqual(overflow.innerWidth);
  expect(blocking, `axe in ${name}`).toEqual([]);
}

const outcome = (page) => page.getByTestId("outcome");
const attemptRows = (page) => page.getByTestId("attempts").locator("li[data-attempt]");
/** The list opens by itself for a failure. In other states it is closed, and a click would close an open one. */
async function openAttempts(page) {
  const details = page.getByTestId("attempts");
  if (!(await details.evaluate((el) => el.open))) await details.locator("summary").click();
}

test.describe.configure({ mode: "serial" });
// A failed test must not leave scripted turns behind for the next one.
test.beforeEach(() => { fs.writeFileSync(queueFile, "[]"); });

/** The question form on the page itself. On desktop the conversation panel shows the same questions beside it. */
const asked = (page) => page.getByRole("region", { name: "What we need from you" });

test("a provider failure is a system failure, keeps its attempt, and retries only when asked", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "provider-503" }, { case: "concrete-thesis" });
  const id = await submit(page, THESIS);

  await expect(outcome(page)).toHaveAttribute("data-outcome", "INVALID_INPUT");
  await expect(page.getByRole("heading", { name: "The interpreter did not answer" })).toBeVisible();
  await expect(page.getByText("This is not a verdict on your idea.")).toBeVisible();
  await expect(page.getByText("Could not be interpreted")).toHaveCount(0);
  await expect(page.getByTestId("failure-detail")).not.toContainText("sk-LEAK");
  await expect(page.getByTestId("attempts")).toBeVisible();
  await expect(attemptRows(page)).toHaveCount(1);
  await expect(attemptRows(page).first()).toContainText("Provider failed");
  await expect(attemptRows(page).first()).toContainText("Unknown");
  expect(remaining(), "nothing retries by itself").toBe(1);
  await shot(page, project, "failure");
  await inspect(page, project, "failure");

  const retry = page.getByRole("button", { name: "Try the interpreter again" });
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: /Trying the interpreter again/ })).toBeVisible();
  await expect(outcome(page)).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION", { timeout: 90_000 });
  await expect(page.locator("#state-title")).toBeFocused();
  await openAttempts(page);
  await expect(attemptRows(page)).toHaveCount(2);
  await expect(attemptRows(page).first()).toContainText("Provider failed"); // the failed attempt stays listed
  await expect(attemptRows(page).nth(1)).toContainText("retry of #1");
  await shot(page, project, "retried");
  record(`p05-failure-retry-${project}`, { id, attempts: 2, remaining: remaining() });
});

test("unusable model output and an unknown outcome are named apart, and an unknown outcome is not retried", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "multiple-objects" });
  const malformed = await submit(page, THESIS);
  await expect(page.getByRole("heading", { name: "The interpreter's answer was not usable" })).toBeVisible();
  await expect(attemptRows(page).first()).toContainText("Rejected: multiple objects");
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toBeVisible();
  await inspect(page, project, "malformed");

  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  script({ case: "provider-hang" });
  const unknown = await submit(page, THESIS);
  await expect(page.getByRole("heading", { name: "We do not know if the interpreter finished" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toHaveCount(0);
  await expect(page.getByTestId("retry-blocked")).toContainText("Nothing was replayed.");
  await expect(attemptRows(page).first()).toContainText(/outcome unknown/);
  await shot(page, project, "unknown");
  await inspect(page, project, "unknown");
  record(`p05-malformed-unknown-${project}`, { malformed, unknown, remaining: remaining() });
});

test("a rough hunch is answered in the user's own words by keyboard, then adopted and saved", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "rough-hunch" }, { follow_up: "hunch-reply-fills-both-rules" });
  const id = await submit(page, HUNCH, /Rough hunch/);
  await expect(outcome(page)).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await expect(asked(page).getByRole("radio", { name: /Price up more than 1% over the last 15 minutes/ })).toBeVisible();
  await inspect(page, project, "needs-answer-words");

  const words = asked(page).getByRole("textbox", { name: /own words.*entry rule/ });
  await words.focus();
  await page.keyboard.type(REPLY_BOTH);
  await page.keyboard.press("Tab");
  await expect(asked(page).getByRole("button", { name: /Send my words.*entry rule/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("working")).toContainText("reading your words");
  await expect(asked(page).getByRole("button", { name: "Adopt these settings" })).toBeVisible({ timeout: 90_000 });
  await expect(page.locator("#state-title")).toBeFocused();
  await page.getByText("Where each setting came from").click();
  const entry = page.getByRole("row", { name: /Entry rule/ });
  await expect(entry).toContainText("You said");
  await expect(entry).toContainText("Enter when price rose more than 2%");
  await openAttempts(page);
  await expect(attemptRows(page)).toHaveCount(2);
  await expect(attemptRows(page).nth(1)).toContainText("Reading your reply");
  await shot(page, project, "words-read");

  await asked(page).getByRole("button", { name: "Adopt these settings" }).click();
  await expect(outcome(page)).toHaveAttribute("data-outcome", "COMPILED");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toBeVisible();
  await inspect(page, project, "saved-after-words");
  record(`p05-words-${project}`, { id, revision: await page.getByTestId("revision-id").textContent(), attempts: 2 });
});

test("a reply with two values is a conflict, and a reply that would change a chosen rule is rejected whole", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "rough-hunch" }, { follow_up: "hunch-reply-states-two-values" });
  const conflictId = await submit(page, HUNCH, /Rough hunch/);
  await asked(page).getByRole("textbox", { name: /own words.*entry rule/ }).fill(REPLY_TWO);
  await asked(page).getByRole("button", { name: /Send my words.*entry rule/ }).click();
  await expect(asked(page).getByRole("textbox", { name: "What should the entry be?" })).toBeVisible({ timeout: 90_000 });
  await page.getByText("Where each setting came from").click();
  await expect(page.getByRole("row", { name: /Entry rule/ })).toContainText("Two statements that disagree");
  await expect(page.getByRole("row", { name: /Entry rule/ })).toContainText("Conflict: needs your answer");
  await shot(page, project, "conflict");
  await inspect(page, project, "conflict");

  await page.goto("/app");
  script({ case: "rough-hunch" }, { follow_up: "reply-overwrites-chosen-entry" });
  const rejectedId = await submit(page, HUNCH, /Rough hunch/);
  await asked(page).getByRole("radio", { name: /Price up more than 1% over the last 15 minutes/ }).check();
  await asked(page).locator('[data-question="choose-entry"]').getByRole("button", { name: "Save my answer" }).click();
  await expect(asked(page).getByRole("radio", { name: /Price up more than 1%/ })).toHaveCount(0);
  await asked(page).getByRole("textbox", { name: /own words.*closed/ }).fill(REPLY_OVERWRITE);
  await asked(page).getByRole("button", { name: /Send my words.*closed/ }).click();
  await expect(page.getByRole("heading", { name: "Your last reply could not be used" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/Your saved meaning did not change/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Try this reply again" })).toBeVisible();
  await page.getByText("Where each setting came from").click();
  await expect(page.getByRole("row", { name: /Entry rule/ })).toContainText("You chose");
  await shot(page, project, "reply-rejected");
  await inspect(page, project, "reply-rejected");
  record(`p05-conflict-overwrite-${project}`, { conflictId, rejectedId });
});

test("an unsupported capability is not a failure, and another owner cannot open or change the request", async ({ page, browser }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "unsupported-extension" });
  const id = await submit(page, LAUNCH_AGE, /Rough hunch/);
  await expect(outcome(page)).toHaveAttribute("data-outcome", "UNSUPPORTED");
  await expect(page.getByText(/token_launch_age_filter/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toHaveCount(0);
  await expect(page.getByText("The interpreter did not answer")).toHaveCount(0);
  await shot(page, project, "unsupported");
  await inspect(page, project, "unsupported");

  const other = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const foreign = await other.newPage();
  await injectAuth(foreign, tokens.b);
  await foreign.goto(`/app#/research/${id}`);
  await expect(foreign.getByText("This request was not found.")).toBeVisible();
  await expect(foreign.getByTestId("attempts")).toHaveCount(0);
  await other.close();
  record(`p05-unsupported-${project}`, { id, queue_left: remaining() });
});

/** Show a saved request as the API would return it if its outcome step had not finished. Only the GET response is changed. */
async function withoutOutcome(page, id, change) {
  await page.route(new RegExp(`/v1/research/requests/${id}$`), async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const bundle = await response.json();
    bundle.outcomes = [];
    bundle.head.outcome = null;
    change(bundle);
    await route.fulfill({ response, json: bundle });
  });
}

test("a request whose outcome was not saved is worded from its attempt, offers the right action and makes no false claim", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "provider-503" });
  const id = await submit(page, THESIS);
  const requests = [];
  page.on("request", (request) => { if (request.method() === "POST") requests.push(request.url()); });

  // A settled provider failure: the retry button must be there.
  await withoutOutcome(page, id, () => {});
  await page.goto(`/app#/research/${id}`);
  await page.reload();
  await expect(outcome(page)).toHaveAttribute("data-reading", "FAILED");
  await expect(page.getByRole("heading", { name: "The interpreter did not answer" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toBeVisible();
  await expect(page.getByText("Could not be interpreted")).toHaveCount(0);
  await shot(page, project, "no-outcome-failed");
  await inspect(page, project, "no-outcome-failed");

  // An attempt with no result: it may be running or stopped, and nothing is offered but a look at the saved record.
  await page.unrouteAll();
  await withoutOutcome(page, id, (bundle) => {
    Object.assign(bundle.attempts[0], { status: "STARTED", completion: "UNKNOWN", finished_at: null, latency_ms: null, parse_result: null,
      usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null }, error_class: null, request_count: null });
    bundle.head.retry = { allowed: false, retry_of: null, reason: "attempt_in_flight" };
  });
  await page.reload();
  await expect(outcome(page)).toHaveAttribute("data-reading", "RUNNING_OR_STOPPED");
  await expect(page.getByTestId("reading-state")).toContainText("may still be running, or it may have stopped");
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Check the saved request again" })).toBeVisible();
  await shot(page, project, "no-outcome-running");
  await inspect(page, project, "no-outcome-running");

  // An accepted answer that was not saved.
  await page.unrouteAll();
  await withoutOutcome(page, id, (bundle) => {
    Object.assign(bundle.attempts[0], { status: "COMPLETED", completion: "COMPLETE", parse_result: "ACCEPTED" });
    bundle.head.retry = { allowed: false, retry_of: null, reason: "nothing_to_retry" };
  });
  await page.reload();
  await expect(outcome(page)).toHaveAttribute("data-reading", "READ_NOT_SAVED");
  await expect(page.getByText("Could not be interpreted")).toHaveCount(0);
  await inspect(page, project, "no-outcome-read-not-saved");

  // An uncertain settlement keeps its blocked-retry reason.
  await page.unrouteAll();
  await withoutOutcome(page, id, (bundle) => {
    Object.assign(bundle.attempts[0], { status: "TIMED_OUT", completion: "UNKNOWN", parse_result: "NOT_PARSED" });
    bundle.head.retry = { allowed: false, retry_of: null, reason: "outcome_uncertain" };
  });
  await page.reload();
  await expect(outcome(page)).toHaveAttribute("data-reading", "UNCERTAIN");
  await expect(page.getByTestId("retry-blocked")).toContainText("Nothing was replayed.");
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toHaveCount(0);
  await inspect(page, project, "no-outcome-uncertain");

  // Looking again reads the saved record and starts nothing.
  const reads = [];
  page.on("request", (request) => { if (request.method() === "GET" && request.url().endsWith(`/v1/research/requests/${id}`)) reads.push(request.url()); });
  await page.getByRole("button", { name: "Check the saved request again" }).click();
  await expect(outcome(page)).toHaveAttribute("data-reading", "UNCERTAIN");
  await expect(page.locator("#state-title")).toBeFocused();
  expect(reads.length, "looking again reads the saved record").toBeGreaterThanOrEqual(1);
  expect(requests, "no write and no interpreter attempt came from looking").toEqual([]);
  expect(remaining()).toBe(0);
  await page.unrouteAll({ behavior: "wait" }); // let any stubbed response finish before the test ends
  record(`p05-no-outcome-${project}`, { id });
});

test("after a retry, the page describes the latest attempt and not an older failure that has its own outcome", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "provider-503" });
  const id = await submit(page, THESIS);
  await expect(page.getByRole("heading", { name: "The interpreter did not answer" })).toBeVisible();

  // Attempt 1 failed and has its outcome. Attempt 2 timed out and its outcome was not saved: only the GET response is changed.
  await page.route(new RegExp(`/v1/research/requests/${id}$`), async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const bundle = await response.json();
    const first = bundle.attempts[0];
    bundle.attempts.push({ ...first, attempt_id: "00000000-0000-4000-8000-0000000000a2", sequence: 2, retry_of: first.attempt_id,
      status: "TIMED_OUT", completion: "UNKNOWN", parse_result: "NOT_PARSED", error_class: null, request_count: null, latency_ms: null,
      usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null } });
    bundle.head.retry = { allowed: false, retry_of: null, reason: "outcome_uncertain" };
    await route.fulfill({ response, json: bundle });
  });
  await page.reload();
  await expect(outcome(page)).toHaveAttribute("data-reading", "UNCERTAIN");
  await expect(page.getByRole("heading", { name: "We do not know if the interpreter finished" })).toBeVisible();
  await expect(page.getByText("The interpreter did not answer")).toHaveCount(0);
  await expect(page.getByText(/did not return a result/)).toHaveCount(0);
  await expect(page.getByTestId("retry-blocked")).toContainText("Nothing was replayed.");
  await shot(page, project, "latest-attempt-unknown");
  await inspect(page, project, "latest-attempt-unknown");
  await page.unrouteAll({ behavior: "wait" });
});

test("the saved-requests list tags each request from its latest attempt and never says 'Could not be interpreted' for a system state", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "provider-503" });
  const id = await submit(page, THESIS);
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  const card = page.locator(`#req-${id}`);
  await expect(card).toContainText("Interpreter did not answer");
  await expect(card).not.toContainText("Could not be interpreted");

  // Attempt 1 failed and has its outcome. Attempt 2 was accepted and its save did not finish: only the list response is changed.
  await page.route(/\/v1\/research\/requests$/, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const body = await response.json();
    const row = body.requests.find((r) => r.intake_record_id === id);
    row.reading.last_covered = false;
    row.reading.retry_allowed = false;
    row.reading.last_attempt = { attempt_id: "00000000-0000-4000-8000-0000000000a2", status: "COMPLETED", parse_result: "ACCEPTED" };
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  await expect(card).toContainText("Read, not saved yet");
  await expect(card).not.toContainText(/Could not be interpreted|did not answer/);
  await shot(page, project, "list-read-not-saved");
  await inspect(page, project, "list-read-not-saved");
  await page.unrouteAll({ behavior: "wait" });
});

test("a no-thesis question with no declared market offers the labelled synthetic market for adoption and ends unresolved", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  script({ case: "bounded-no-thesis" });
  const id = await submit(page, "I have no view. Look at this market over the last two days and tell me whether anything is worth testing.", /No thesis/);
  await expect(outcome(page)).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await expect(asked(page).getByText(/Review the suggested settings/)).toBeVisible();
  await expect(asked(page).getByText("Synthetic fixture market (not a real pool)")).toBeVisible();
  await expect(asked(page).getByRole("textbox")).toHaveCount(0); // no question the user must answer in words
  await expect(page.getByText(/before the investigation can be reviewed/)).toBeVisible();
  await inspect(page, project, "no-thesis-undeclared-market");
  await asked(page).getByRole("button", { name: "Adopt these settings" }).click();
  await expect(outcome(page)).toHaveAttribute("data-outcome", "UNRESOLVED");
  await shot(page, project, "no-thesis-adopted");
  await inspect(page, project, "no-thesis-adopted");
  record(`p05-undeclared-market-${project}`, { id });
});
