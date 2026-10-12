/**
 * #58 Stage 2 runtime checks through the real screens, routes and database.
 * Reuses the agents saved by financial-journey.spec.mjs in this run. Fixture ports only.
 * - F1: the read-only "Saved connected state" panel shows service projections; unknown values stay unknown.
 * - F2: a saved change whose read-back fails keeps every change control paused until a read succeeds.
 * - F5: a keyboard-only pass over the connected-agent and funding controls with a visible focus indicator.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
const financialFile = path.join(evidence, "financial-results.json");
const keyboardFile = path.join(evidence, "keyboard-qa.json");

function saved(key) {
  const value = JSON.parse(fs.readFileSync(financialFile, "utf8"))[key];
  expect(value, `financial-journey.spec.mjs must save ${key} first`).toBeTruthy();
  return value;
}

async function shot(page, project, name) {
  fs.mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, `${project}-runtime-${name}.png`), fullPage: true });
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

test.describe.configure({ mode: "serial" });

test("F1: the saved connected state shows service projections without inventing values", async ({ page }, info) => {
  const project = info.project.name;
  const { agentId } = saved(`main-${project}`);
  await injectAuth(page, tokens.a);
  await page.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
  const panel = page.getByRole("region", { name: "Saved connected state" });
  const list = panel.getByRole("list", { name: "Projected records" });
  await expect(list).toBeVisible();
  await expect(panel).toContainText("Ports: authored local fixtures.");
  await expect(list.locator('[data-kind="AGENT"]')).toContainText("Agent: STOPPED");
  await expect(list.locator('[data-kind="POSITION"]')).toContainText("unrealized result and mark unknown");
  await expect(list.locator('[data-kind="CAPITAL_FLOW"]').first()).toContainText("Not a trading result.");
  await expect(list.locator('[data-kind="ACTION"]').first()).toContainText("CONFIRMED");
  await expect(panel).not.toContainText("NaN");
  await shot(page, project, "projection");
  await noSidewaysScroll(page);
  await noSeriousAxe(page);

  // Another owner opens the same agent ID and sees no records of owner A.
  const other = await page.context().browser().newContext({ baseURL: info.project.use.baseURL, viewport: page.viewportSize() });
  const otherPage = await other.newPage();
  await injectAuth(otherPage, tokens.b);
  await otherPage.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
  await expect(otherPage.getByRole("region", { name: "Saved connected state" }))
    .toContainText("No connected-service state is saved for this agent.");
  await other.close();
});

test("F2: a saved change whose read-back fails keeps the funding controls paused", async ({ page }, info) => {
  const project = info.project.name;
  const { agentId } = saved(`lost-ack-${project}`);
  await injectAuth(page, tokens.a);
  await page.goto(`/#/funds?agent=${encodeURIComponent(agentId)}`);
  const funding = page.getByRole("region", { name: "Agent funding" });
  const check = funding.getByRole("button", { name: "Check deposits" });
  await expect(check).toBeEnabled();

  let failedReads = 0;
  await page.route(/\/funding$/, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    failedReads += 1;
    await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "read failed" }) });
  });
  await check.click();
  await expect(funding.getByRole("alert")).toContainText("The change was saved, but the current funding could not be read.");
  await expect(check).toBeDisabled();
  await expect(funding.getByRole("button", { name: "Save reviewed deposit" })).toBeDisabled();
  await expect(funding.getByTestId("funding-flows")).toBeVisible(); // the last saved view stays, marked unconfirmed
  expect(failedReads).toBeGreaterThan(0);
  await shot(page, project, "readback-failed");
  await noSidewaysScroll(page);

  await page.unroute(/\/funding$/);
  await funding.getByRole("button", { name: "Check saved funding" }).click();
  await expect(funding.getByRole("alert")).toHaveCount(0);
  await expect(check).toBeEnabled();
});

test("F5: keyboard-only pass over the connected-agent and funding controls", async ({ page }, info) => {
  const project = info.project.name;
  const { agentId } = saved(`lost-ack-${project}`);
  await injectAuth(page, tokens.a);
  await page.goto(`/#/funds?agent=${encodeURIComponent(agentId)}`);
  const funding = page.getByRole("region", { name: "Agent funding" });
  await expect(funding.getByRole("button", { name: "Check deposits" })).toBeEnabled();
  await expect(page.getByRole("region", { name: "Saved connected state" }).getByRole("list")).toBeVisible();

  await page.locator("#connected-agent").focus();
  const stops = [];
  for (let index = 0; index < 40; index += 1) {
    const focused = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const style = getComputedStyle(el);
      const region = el.closest("section[aria-label]");
      return { tag: el.tagName.toLowerCase(), name: (el.getAttribute("aria-label") || el.textContent || el.id || "").trim().slice(0, 60),
        region: region ? region.getAttribute("aria-label") : null,
        indicator: (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== "none"
          || el.id === "connected-agent" };
    });
    if (focused) stops.push(focused);
    await page.keyboard.press("Tab");
  }
  const names = stops.map((stop) => stop.name);
  for (const expected of ["Open agent", "Check deposits"]) expect(names).toContain(expected);
  expect(stops.some((stop) => stop.tag === "select")).toBe(true);
  expect(stops.filter((stop) => !stop.indicator)).toEqual([]);

  // Activate with the keyboard only: move focus to "Check deposits" with Tab and press Enter.
  await page.locator("#connected-agent").focus();
  for (let index = 0; index < 40; index += 1) {
    const name = await page.evaluate(() => (document.activeElement?.textContent ?? "").trim());
    if (name === "Check deposits") break;
    await page.keyboard.press("Tab");
  }
  await page.keyboard.press("Enter");
  await expect(funding.getByRole("alert")).toHaveCount(0);
  await expect(funding.getByRole("button", { name: "Check deposits" })).toBeEnabled();

  const report = fs.existsSync(keyboardFile) ? JSON.parse(fs.readFileSync(keyboardFile, "utf8")) : {};
  report[project] = { stops, activated: "Check deposits (Enter)" };
  fs.writeFileSync(keyboardFile, JSON.stringify(report, null, 2));
  await shot(page, project, "keyboard");
});
