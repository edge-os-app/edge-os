/**
 * Interface quality checks (browser-qa phases and the accepted P43 control size), run with the e2e specs.
 * Evidence: smoke, control and axe results are written under P03_EVIDENCE_DIR/quality.
 * An axe run covers part of WCAG. It does not replace keyboard, screen reader or phone checks.
 */
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const outDir = path.join(evidence, "quality");
fs.mkdirSync(outDir, { recursive: true });
const sample = (page, text) => page.locator("button.example", { hasText: text });
const MIN = 44;

async function open(page, token) {
  await injectAuth(page, token);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
}

/** Visible interactive controls whose hit area is smaller than the accepted 44px minimum. */
async function smallControls(page) {
  return page.evaluate((min) => {
    const selector = 'button, a[href], summary, select, textarea, input:not([type="hidden"]), [role="button"]';
    const small = [];
    for (const el of document.querySelectorAll(selector)) {
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      // Radios and checkboxes are hit through their label.
      const box = (el.matches('input[type="radio"], input[type="checkbox"]') ? el.closest("label") ?? el : el).getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      if (box.right < 0 || box.bottom < 0 || box.left > innerWidth + 1000) continue; // off-screen skip link
      if (el.closest("dialog:not([open])")) continue;
      const iconOnly = !el.textContent.trim() || el.textContent.trim().length <= 2;
      if (box.height < min - 0.5 || (iconOnly && box.width < min - 0.5)) {
        small.push({ tag: el.tagName, label: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 50),
          width: Math.round(box.width), height: Math.round(box.height) });
      }
    }
    return small;
  }, MIN);
}


test("accepted 44px minimum holds on every control in the main states", async ({ page }, info) => {
  const results = {};
  await open(page, tokens.a);
  await page.getByRole("button", { name: /Add “no leverage”/ }).click();
  await page.getByRole("button", { name: /Add “no additions”/ }).click();
  results.homeWithRestrictions = await smallControls(page);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.locator("summary", { hasText: "Where each setting came from" }).click();
  results.requestWithDetailsOpen = await smallControls(page);
  if (info.project.name === "mobile-390") {
    await page.getByRole("button", { name: "Conversation" }).click();
    results.conversationSheet = await smallControls(page);
    await page.keyboard.press("Escape");
  }
  fs.writeFileSync(path.join(outDir, `controls-${info.project.name}.json`), JSON.stringify(results, null, 2));
  expect(results, JSON.stringify(results)).toEqual({ homeWithRestrictions: [], requestWithDetailsOpen: [], ...(info.project.name === "mobile-390" ? { conversationSheet: [] } : {}) });
});

test("smoke: the main path raises no console error, page error or failed request", async ({ page }, info) => {
  const problems = [];
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("response", (r) => { if (r.status() >= 400) problems.push(`http ${r.status()} ${r.url()}`); });
  page.on("requestfailed", (r) => problems.push(`failed ${r.url()}`));
  await open(page, tokens.a);
  await sample(page, "Specific thesis").click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.locator("main").getByRole("button", { name: "Adopt these settings" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toBeVisible();
  await page.getByRole("button", { name: "All requests" }).click();
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  for (const area of ["Agents", "Positions", "Funds", "Research"]) {
    await page.getByRole("button", { name: area, exact: true }).click();
  }
  fs.writeFileSync(path.join(outDir, `smoke-${info.project.name}.json`), JSON.stringify({ problems }, null, 2));
  expect(problems).toEqual([]);
});

test("axe: no serious or critical WCAG 2.2 AA violation in the main states", async ({ page }, info) => {
  const report = {};
  const scan = async (name) => {
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    report[name] = result.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) }));
  };
  await open(page, tokens.a);
  await scan("home");
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await scan("needs-answer");
  await page.locator("main").getByRole("button", { name: "Adopt these settings" }).click();
  await page.locator("main").getByRole("radio", { name: /more than 2% over the last 15 minutes/ }).check();
  await page.locator("main").getByRole("button", { name: "Save my answer" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await scan("review");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toBeVisible();
  await scan("saved");
  await page.getByRole("button", { name: "All requests" }).click();
  await sample(page, /I have no view/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNRESOLVED");
  await scan("unresolved");
  fs.writeFileSync(path.join(outDir, `axe-${info.project.name}.json`), JSON.stringify(report, null, 2));
  const serious = Object.entries(report).flatMap(([state, list]) => list.filter((v) => ["serious", "critical"].includes(v.impact)).map((v) => ({ state, ...v })));
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

test("modal conversation keeps focus after an answer and after adoption", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile-390", "the modal sheet exists below 1181px");
  await open(page, tokens.a);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  const trigger = page.getByRole("button", { name: "Conversation" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Conversation" });
  await expect(dialog).toBeVisible();
  const inDialog = () => page.evaluate(() => !!document.activeElement?.closest("dialog") && document.activeElement !== document.body);
  // answer the entry choice inside the dialog with the keyboard
  await dialog.getByRole("radio", { name: /more than 1% over the last 15 minutes/ }).focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(dialog.getByRole("radio", { name: /more than 2%/ })).toHaveCount(0);
  await expect.poll(inDialog, { message: "focus must stay in the dialog after the answer" }).toBe(true);
  // adopt the remaining settings inside the dialog
  await dialog.getByRole("button", { name: "Adopt these settings" }).focus();
  await page.keyboard.press("Enter");
  await expect(dialog.getByText("No question is open for this revision.")).toBeVisible();
  await expect.poll(inDialog, { message: "focus must stay in the dialog after adoption" }).toBe(true);
  for (let i = 0; i < 8; i++) { await page.keyboard.press("Tab"); expect(await inDialog()).toBe(true); }
  for (let i = 0; i < 8; i++) { await page.keyboard.press("Shift+Tab"); expect(await inDialog()).toBe(true); }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("side panel answer keeps focus in the side panel on desktop", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the persistent side panel exists from 1181px");
  await open(page, tokens.a);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  const side = page.locator(".convo-desktop");
  await side.getByRole("radio", { name: /more than 3% over the last 30 minutes/ }).check();
  await side.getByRole("button", { name: "Save my answer" }).click();
  await expect(side.getByRole("log")).toContainText("Entry rule");
  expect(await page.evaluate(() => !!document.activeElement?.closest(".convo-desktop") && document.activeElement !== document.body)).toBe(true);
});
