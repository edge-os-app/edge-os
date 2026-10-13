/**
 * HERMES-MOUNT: the Research path over the LOCAL Hermes transport mount
 * (`scripts/hermes_app_mount/serve_transport_mount.py`). Each turn runs ACTUAL pinned Hermes in a no-network job whose one
 * request goes through the accepted guard and the AUTHORED transport; spend goes to the shared PostgreSQL ledger. The
 * provider answers from a queue this spec fills, so every state is authored. Evidence: `hermes-mount-results.json`,
 * `screenshots/*-mount-*`.
 */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
fs.mkdirSync(shots, { recursive: true });
const resultsFile = path.join(evidence, "hermes-mount-results.json");
const queueFile = process.env.HERMES_MOUNT_SCRIPT_FILE;
const THESIS = "Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. Spot only.";

function record(key, value) {
  const current = fs.existsSync(resultsFile) ? JSON.parse(fs.readFileSync(resultsFile, "utf8")) : {};
  current[key] = value;
  fs.writeFileSync(resultsFile, JSON.stringify(current, null, 2));
}
function script(...items) {
  fs.writeFileSync(queueFile, JSON.stringify([...JSON.parse(fs.readFileSync(queueFile, "utf8")), ...items]));
}
const remaining = () => JSON.parse(fs.readFileSync(queueFile, "utf8")).length;
const outcome = (page) => page.getByTestId("outcome");
const rows = (page) => page.getByTestId("attempts").locator("li[data-attempt]");
async function openAttempts(page) {
  const details = page.getByTestId("attempts");
  if (!(await details.evaluate((el) => el.open))) await details.locator("summary").click();
}
async function submit(page, token, text) {
  await injectAuth(page, token);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  await page.getByLabel("Your words", { exact: true }).fill(text);
  await page.getByRole("radio", { name: /Specific rule or thesis/ }).check();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(outcome(page)).toBeVisible({ timeout: 90_000 });
  return page.url().split("/research/")[1];
}

/** Page errors and server errors during a drive (browser-qa smoke check); an expected 404 for another owner is not one. */
function watch(page) {
  const problems = [];
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("response", (response) => { if (response.status() >= 500) problems.push(`${response.status()} ${response.url()}`); });
  return problems;
}

test.describe.configure({ mode: "serial" });
test.beforeEach(() => { fs.writeFileSync(queueFile, "[]"); });

test("a saved request runs the mounted Hermes once, shows its attempt and usage, and reopens in a new context", async ({ page, browser }, info) => {
  const project = info.project.name;
  const problems = watch(page);
  script({ case: "concrete-thesis" });
  const id = await submit(page, tokens.a, THESIS);

  await expect(outcome(page)).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await openAttempts(page);
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toContainText("Finished");
  await expect(rows(page).first()).toContainText("1,423 in, 611 out");
  const attempt = await rows(page).first().getAttribute("data-attempt");
  expect(remaining(), "one job consumed one authored reply").toBe(0);
  await page.screenshot({ path: path.join(shots, `${project}-mount-completed.png`), fullPage: true });

  // The browser is closed; the same owner reopens the record in a new context and nothing is written.
  const again = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const reopened = await again.newPage();
  const writes = [];
  reopened.on("request", (request) => { if (request.method() !== "GET") writes.push(`${request.method()} ${request.url()}`); });
  await injectAuth(reopened, tokens.a);
  await reopened.goto(`/#/research/${id}`);
  await expect(outcome(reopened)).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION", { timeout: 30_000 });
  await openAttempts(reopened);
  await expect(rows(reopened)).toHaveCount(1);
  await expect(rows(reopened).first()).toHaveAttribute("data-attempt", attempt);
  await expect(rows(reopened).first()).toContainText("1,423 in, 611 out");
  expect(writes, "reopening makes no write and starts no turn").toEqual([]);
  await again.close();

  const other = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const foreign = await other.newPage();
  await injectAuth(foreign, tokens.b);
  await foreign.goto(`/#/research/${id}`);
  await expect(foreign.getByText("This request was not found.")).toBeVisible();
  await expect(foreign.getByTestId("attempts")).toHaveCount(0);
  await other.close();
  expect(problems, "no page error or server error").toEqual([]);
  record(`mount-completed-${project}`, { id, attempt });
});

test("a lost provider reply is an unknown outcome, is not accepted and is not retried", async ({ page }, info) => {
  const project = info.project.name;
  const problems = watch(page);
  script({ case: "concrete-thesis", transport_fault: "lost_reply" });
  const id = await submit(page, tokens.a, THESIS);

  await expect(page.getByRole("heading", { name: "We do not know if the interpreter finished" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toHaveCount(0);
  await openAttempts(page);
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toContainText("Outcome unknown");
  const attempt = await rows(page).first().getAttribute("data-attempt");
  expect(remaining()).toBe(0);
  await page.screenshot({ path: path.join(shots, `${project}-mount-lost.png`), fullPage: true });
  expect(problems, "no page error or server error").toEqual([]);
  record(`mount-lost-${project}`, { id, attempt });
});
