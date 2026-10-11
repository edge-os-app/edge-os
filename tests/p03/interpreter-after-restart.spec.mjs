/**
 * P05: after the API restarts on the same database, a new browser context shows the same saved attempts and states.
 * Reads the ids that `interpreter.spec.mjs` recorded. It makes no POST and starts no interpreter turn.
 */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const results = JSON.parse(fs.readFileSync(path.join(evidence, "p05-results.json"), "utf8"));
const outcome = (page) => page.getByTestId("outcome");
const rows = (page) => page.getByTestId("attempts").locator("li[data-attempt]");
async function openAttempts(page) {
  const details = page.getByTestId("attempts");
  if (!(await details.evaluate((el) => el.open))) await details.locator("summary").click();
}

test.describe.configure({ mode: "serial" });

test("saved attempts and states reopen unchanged in a fresh context", async ({ browser }, info) => {
  const project = info.project.name;
  const posts = [];
  const context = await browser.newContext({ viewport: info.project.use.viewport, hasTouch: info.project.use.hasTouch });
  const page = await context.newPage();
  page.on("request", (request) => { if (request.method() !== "GET") posts.push(`${request.method()} ${request.url()}`); });
  await injectAuth(page, tokens.a);
  const open = async (id) => { await page.goto(`/#/research/${id}`); await expect(outcome(page)).toBeVisible({ timeout: 30_000 }); };

  const failure = results[`p05-failure-retry-${project}`];
  await open(failure.id);
  await expect(outcome(page)).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await openAttempts(page);
  await expect(rows(page)).toHaveCount(2);
  await expect(rows(page).first()).toContainText("Provider failed");
  await expect(rows(page).nth(1)).toContainText("retry of #1");

  const unknown = results[`p05-malformed-unknown-${project}`];
  await open(unknown.unknown);
  await expect(page.getByRole("heading", { name: "We do not know if the interpreter finished" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toHaveCount(0);
  await open(unknown.malformed);
  await expect(page.getByRole("heading", { name: "The interpreter's answer was not usable" })).toBeVisible();

  const words = results[`p05-words-${project}`];
  await open(words.id);
  await expect(page.getByTestId("revision-id")).toHaveText(words.revision);
  await openAttempts(page);
  await expect(rows(page)).toHaveCount(2);

  const rejected = results[`p05-conflict-overwrite-${project}`];
  await open(rejected.rejectedId);
  await expect(page.getByRole("heading", { name: "Your last reply could not be used" })).toBeVisible();
  await open(rejected.conflictId);
  await page.getByText("Where each setting came from").click();
  await expect(page.getByRole("row", { name: /Entry rule/ })).toContainText("Two statements that disagree");

  expect(posts, "reopening makes no write and starts no interpreter turn").toEqual([]);
  await context.close();
});
