/**
 * HERMES-MOUNT: after the mount's API process restarts with the same run id on the same database, a new browser context
 * shows the same saved attempts and states. Reads the ids that `hermes-transport-mount.spec.mjs` recorded. It makes no write.
 */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const results = JSON.parse(fs.readFileSync(path.join(evidence, "hermes-mount-results.json"), "utf8"));
const outcome = (page) => page.getByTestId("outcome");
const rows = (page) => page.getByTestId("attempts").locator("li[data-attempt]");
async function openAttempts(page) {
  const details = page.getByTestId("attempts");
  if (!(await details.evaluate((el) => el.open))) await details.locator("summary").click();
}

test("mounted attempts reopen unchanged after the mount process restarts", async ({ browser }, info) => {
  const project = info.project.name;
  const context = await browser.newContext({ viewport: info.project.use.viewport, hasTouch: info.project.use.hasTouch });
  const page = await context.newPage();
  const writes = [];
  page.on("request", (request) => { if (request.method() !== "GET") writes.push(`${request.method()} ${request.url()}`); });
  await injectAuth(page, tokens.a);

  const completed = results[`mount-completed-${project}`];
  await page.goto(`/#/research/${completed.id}`);
  await expect(outcome(page)).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION", { timeout: 30_000 });
  await openAttempts(page);
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toHaveAttribute("data-attempt", completed.attempt);
  await expect(rows(page).first()).toContainText("1,423 in, 611 out");

  const lost = results[`mount-lost-${project}`];
  await page.goto(`/#/research/${lost.id}`);
  await expect(page.getByRole("heading", { name: "We do not know if the interpreter finished" })).toBeVisible({ timeout: 30_000 });
  await openAttempts(page);
  await expect(rows(page).first()).toHaveAttribute("data-attempt", lost.attempt);
  await expect(page.getByRole("button", { name: "Try the interpreter again" })).toHaveCount(0);

  expect(writes, "reopening makes no write and starts no turn").toEqual([]);
  await context.close();
});
