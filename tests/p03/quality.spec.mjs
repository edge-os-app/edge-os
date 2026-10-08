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


/** WCAG contrast of text against the nearest opaque background, including ::placeholder and translucent colors. */
async function lowContrast(page) {
  return page.evaluate(() => {
    const parse = (value) => {
      const m = value.match(/^rgba?\(([^)]+)\)$/) ?? null;
      if (m) { const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p[3] ?? 1 }; }
      const c = value.match(/^color\(srgb ([^)]+)\)$/);
      if (c) { const p = c[1].split(/[ /]+/).filter(Boolean).map(Number); return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p[3] ?? 1 }; }
      return null;
    };
    const over = (top, bottom) => ({ r: top.r * top.a + bottom.r * (1 - top.a), g: top.g * top.a + bottom.g * (1 - top.a), b: top.b * top.a + bottom.b * (1 - top.a), a: 1 });
    const background = (el) => {
      const layers = [];
      for (let node = el; node; node = node.parentElement) {
        const bg = parse(getComputedStyle(node).backgroundColor);
        if (bg && bg.a > 0) { layers.push(bg); if (bg.a === 1) break; }
      }
      let base = { r: 255, g: 255, b: 255, a: 1 };
      for (const layer of layers.reverse()) base = over(layer, base);
      return base;
    };
    const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
    const ratio = (fg, bg) => { const a = lum(fg), b = lum(bg); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
    const checks = [];
    const selectors = ".muted, .eyebrow, .msg .who, dl.kv dt, table.records th, .tag, .chip, .status, .notice, .choice, .example, .card-open, label, legend, h1, h2, h3, p, summary";
    for (const el of document.querySelectorAll(selectors)) {
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none" || !el.getBoundingClientRect().width || !el.textContent.trim()) continue;
      if (el.closest("dialog:not([open])") || el.classList.contains("visually-hidden")) continue;
      const bg = background(el), fg = parse(style.color);
      if (!fg) continue;
      const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700);
      checks.push({ what: `${el.tagName.toLowerCase()}.${el.className}`.slice(0, 40), text: el.textContent.trim().slice(0, 24), ratio: ratio(over(fg, bg), bg), min: large ? 3 : 4.5 });
    }
    for (const el of document.querySelectorAll("input.input, textarea.input")) {
      const fg = parse(getComputedStyle(el, "::placeholder").color);
      if (fg && el.getBoundingClientRect().width) { const bg = background(el); checks.push({ what: `placeholder ${el.tagName.toLowerCase()}`, text: el.id.slice(-12), ratio: ratio(over(fg, bg), bg), min: 4.5 }); }
    }
    return checks.filter((c) => c.ratio < c.min).map((c) => ({ ...c, ratio: Math.round(c.ratio * 100) / 100 }));
  });
}

test("text and placeholder contrast meet 4.5:1 (3:1 for large text) in the main states", async ({ page }, info) => {
  const failures = {};
  await open(page, tokens.a);
  failures.home = await lowContrast(page);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  failures.needsAnswer = await lowContrast(page);
  fs.writeFileSync(path.join(outDir, `contrast-${info.project.name}.json`), JSON.stringify(failures, null, 2));
  expect(failures, JSON.stringify(failures, null, 2)).toEqual({ home: [], needsAnswer: [] });
});

test("no horizontal scroll with long unbroken text, at any width", async ({ page }, info) => {
  await open(page, tokens.a);
  const long = `Is 0x1111111111111111111111111111111111111111 ${"x".repeat(140)} worth testing?`;
  await page.getByLabel("Your words", { exact: true }).fill(long);
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toBeVisible();
  const overflow = async () => page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }));
  const requestPage = await overflow();
  await page.getByRole("button", { name: "All requests" }).click();
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  await expect(page.locator("button.card-open").first()).toBeVisible();
  const home = await overflow();
  fs.writeFileSync(path.join(outDir, `overflow-${info.project.name}.json`), JSON.stringify({ requestPage, home }, null, 2));
  expect(requestPage.scrollWidth).toBeLessThanOrEqual(requestPage.innerWidth);
  expect(home.scrollWidth).toBeLessThanOrEqual(home.innerWidth);
});
