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

async function saveSpotReplay(page) {
  const replay = page.getByTestId("spot-replay");
  await replay.getByRole("button", { name: "Add entry dependency" }).click();
  await replay.getByRole("button", { name: "Add entry dependency" }).click();
  await replay.getByLabel("entry dependency offset 2").fill("-3");
  await replay.getByRole("button", { name: "Add exit dependency" }).click();
  await replay.getByRole("button", { name: "Add exit dependency" }).click();
  await replay.getByLabel("exit dependency offset 2").fill("-1");
  await replay.getByLabel("I reviewed the entry dependency set").check();
  await replay.getByLabel("I reviewed the exit dependency set").check();
  await replay.getByRole("button", { name: "Save synthetic replay" }).click();
  await expect(replay.getByTestId("spot-replay-result")).toContainText("Saved replay: complete");
  return replay;
}

async function publishSpotReplayStrategy(page) {
  await page.getByRole("button", { name: "All requests" }).click();
  await sample(page, "Specific thesis").click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toBeVisible();
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
  await publishSpotReplayStrategy(page);
  await saveSpotReplay(page);
  results.spotReplay = await smallControls(page);
  fs.writeFileSync(path.join(outDir, `controls-${info.project.name}.json`), JSON.stringify(results, null, 2));
  expect(results, JSON.stringify(results)).toEqual({ homeWithRestrictions: [], requestWithDetailsOpen: [], spotReplay: [], ...(info.project.name === "mobile-390" ? { conversationSheet: [] } : {}) });
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
    await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: area, exact: true }).click();
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
  await saveSpotReplay(page);
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

test("P08 investigation review controls and accessibility", async ({ page }, info) => {
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill("Compare bounded descriptive cohorts in a synthetic fixture.");
  await page.getByRole("radio").nth(2).check();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("investigation-review")).toBeVisible();
  const small = await smallControls(page);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const serious = result.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  fs.writeFileSync(path.join(outDir, `p08-review-${info.project.name}.json`), JSON.stringify({ small,
    violations: result.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help })) }, null, 2));
  expect(small, JSON.stringify(small)).toEqual([]);
  expect(serious, JSON.stringify(serious.map((v) => ({ id: v.id, help: v.help, impact: v.impact })), null, 2)).toEqual([]);
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
  if (info.project.name === "mobile-390") {
    await page.getByRole("button", { name: "Conversation" }).click();
    failures.conversationSheet = await lowContrast(page);
    await page.keyboard.press("Escape");
  }
  await page.locator("main").getByRole("button", { name: "Adopt these settings" }).click();
  await page.locator("main").getByRole("radio", { name: /more than 2% over the last 15 minutes/ }).check();
  await page.locator("main").getByRole("button", { name: "Save my answer" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  failures.compiled = await lowContrast(page);
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toBeVisible();
  await saveSpotReplay(page);
  failures.saved = await lowContrast(page);
  await page.getByRole("button", { name: "All requests" }).click();
  await sample(page, /I have no view/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNRESOLVED");
  failures.unresolved = await lowContrast(page);
  fs.writeFileSync(path.join(outDir, `contrast-${info.project.name}.json`), JSON.stringify(failures, null, 2));
  const clean = Object.fromEntries(Object.keys(failures).map((state) => [state, []]));
  expect(Object.keys(clean).length).toBeGreaterThanOrEqual(5);
  expect(failures, JSON.stringify(failures, null, 2)).toEqual(clean);
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

const alerts = (page) => page.locator('[role="alert"]:not(#__next-route-announcer__)');
const inView = (page, locator) => locator.evaluate((el) => { const r = el.getBoundingClientRect(); return r.top >= -1 && r.bottom <= window.innerHeight + 1; });
// The scroll happens in an effect right after the text appears, so wait for it rather than sampling once.
const expectInView = async (page, locator, message) => {
  try { await expect.poll(() => inView(page, locator), { message, timeout: 4000 }).toBe(true); }
  catch (error) {
    const metrics = await locator.evaluate((el) => { const r = el.getBoundingClientRect(); const dlg = el.closest("dialog"); return { top: r.top, bottom: r.bottom, innerHeight: window.innerHeight, scrollY: window.scrollY, docHeight: document.documentElement.scrollHeight, inDialog: !!dlg, dialogScrollTop: dlg?.scrollTop ?? null, dialogHeight: dlg?.getBoundingClientRect().height ?? null, text: el.textContent.slice(0, 60) }; });
    fs.writeFileSync(path.join(outDir, `not-in-view-${Date.now()}.json`), JSON.stringify({ message, metrics }, null, 2));
    throw error;
  }
};

test("a failed answer or save keeps focus on the pressed button and shows the error in view", async ({ page }, info) => {
  await open(page, tokens.a);
  await sample(page, "Specific thesis").click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  const unavailable = { status: 503, contentType: "application/json", body: JSON.stringify({ code: "service_unavailable", findings: [{ detail: "A required service is unavailable. Retry later." }] }) };
  // 1. a failed answer
  await page.route("**/clarifications", (route) => route.fulfill(unavailable));
  const adopt = page.locator("main").getByRole("button", { name: "Adopt these settings" });
  await adopt.focus();
  await page.keyboard.press("Enter");
  await expect(alerts(page)).toContainText("unavailable");
  await expect(adopt).toBeFocused();
  await expectInView(page, alerts(page).first(), "the error must be on screen");
  await page.unroute("**/clarifications");
  await page.keyboard.press("Enter"); // retry works and the answer succeeds
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  // 2. a failed save
  await page.route("**/revisions", (route) => route.request().method() === "POST" ? route.fulfill(unavailable) : route.continue());
  const save = page.getByRole("button", { name: "Save this revision" });
  await save.focus();
  await page.keyboard.press("Enter");
  await expect(alerts(page)).toContainText("unavailable");
  await expect(save).toBeFocused();
  await expectInView(page, alerts(page).first(), "the save error must be on screen");
  await page.unroute("**/revisions");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("revision")).toBeVisible();
  await expect(page.locator("#state-title")).toBeFocused();
  await page.screenshot({ path: path.join(outDir, `failure-recovery-${info.project.name}.png`), fullPage: true });
});

test("the keyboard focus ring has at least 3:1 contrast on every surface it appears on", async ({ page }, info) => {
  await open(page, tokens.a);
  await page.keyboard.press("Tab"); // keyboard modality, so :focus-visible applies
  const targets = [page.getByRole("button", { name: "Agents", exact: true }), page.getByLabel("Your words", { exact: true }),
    page.getByRole("button", { name: "Prepare request" }), page.getByRole("button", { name: /Add “no leverage”/ })];
  const results = [];
  for (const target of targets) {
    await target.focus();
    results.push(await target.evaluate((el) => {
      const parse = (v) => { const m = v.match(/^rgba?\(([^)]+)\)$/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p[3] ?? 1 }; };
      const bgOf = (node) => { for (let n = node; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) return c; } return { r: 255, g: 255, b: 255, a: 1 }; };
      const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
      const style = getComputedStyle(el), ring = parse(style.outlineColor), bg = bgOf(el.parentElement ?? el);
      const ratio = ring ? (Math.max(lum(ring), lum(bg)) + 0.05) / (Math.min(lum(ring), lum(bg)) + 0.05) : 0;
      return { what: (el.getAttribute("aria-label") || el.textContent || el.id).trim().slice(0, 30), outline: style.outlineStyle, ratio: Math.round(ratio * 100) / 100, visible: el.matches(":focus-visible") };
    }));
  }
  fs.writeFileSync(path.join(outDir, `focus-ring-${info.project.name}.json`), JSON.stringify(results, null, 2));
  for (const r of results) { expect(r.visible, JSON.stringify(r)).toBe(true); expect(r.outline, JSON.stringify(r)).not.toBe("none"); expect(r.ratio, JSON.stringify(r)).toBeGreaterThanOrEqual(3); }
});

/** Detect mid-word wraps while allowing a hyphenated compound to wrap at its valid hyphen break. */
async function splitWords(page) {
  return page.evaluate(() => {
    const roots = document.querySelectorAll("table.records th, table.records td, h1, h2, h3, button, label.choice, legend, .status, .tag, .notice, .convo p, .panel p, summary, dt");
    const split = [];
    for (const root of roots) {
      if (root.closest("dialog:not([open])") || root.classList.contains("visually-hidden")) continue;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        for (const match of node.data.matchAll(/[^\s-]+/g)) {
          if (match[0].length > 24) continue;
          const range = document.createRange();
          range.setStart(node, match.index); range.setEnd(node, match.index + match[0].length);
          const tops = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top / 4)));
          if (tops.size > 1) split.push(match[0]);
        }
      }
    }
    return [...new Set(split)];
  });
}

test("word-split check allows a hyphen break but still catches breaks inside a word segment", async ({ page }) => {
  await page.setContent(`<style>body{font:16px Arial} .panel{width:60px} .panel p{overflow-wrap:anywhere}</style>
    <section class="panel"><p>10-minute</p><p>internationalization</p></section>`);
  const found = await splitWords(page);
  expect(found).toContain("internationalization");
  expect(found).not.toContain("10");
  expect(found).not.toContain("minute");
});

test("no word segment is split in the middle in the main states", async ({ page }, info) => {
  const found = {};
  await open(page, tokens.a);
  found.home = await splitWords(page);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  found.needsAnswer = await splitWords(page);
  await page.locator("main").getByRole("button", { name: "Adopt these settings" }).click();
  await page.locator("main").getByRole("radio", { name: /more than 2% over the last 15 minutes/ }).check();
  await page.locator("main").getByRole("button", { name: "Save my answer" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  found.review = await splitWords(page);
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toBeVisible();
  await saveSpotReplay(page);
  await page.locator("summary", { hasText: "Where each setting came from" }).click();
  found.saved = await splitWords(page);
  fs.writeFileSync(path.join(outDir, `split-words-${info.project.name}.json`), JSON.stringify(found, null, 2));
  expect(found, JSON.stringify(found)).toEqual({ home: [], needsAnswer: [], review: [], saved: [] });
});

test("a late focus return never steals focus from a field the person is typing in", async ({ page }, info) => {
  await open(page, tokens.a);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toBeVisible();
  // the saved list answers slowly, so the return-focus target appears late
  await page.route("**/v1/research/requests", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await new Promise((resolve) => setTimeout(resolve, 1500));
    return route.continue();
  });
  await page.getByRole("button", { name: "All requests" }).click();
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  const words = page.getByLabel("Your words", { exact: true });
  await words.click();
  await page.keyboard.type("still typing");
  await page.waitForTimeout(2200); // the list arrives and the old target now exists
  await expect(words).toBeFocused();
  await expect(words).toHaveValue("still typing");
  await page.unroute("**/v1/research/requests");
});

const unavailable = { status: 503, contentType: "application/json", body: JSON.stringify({ code: "service_unavailable", findings: [{ detail: "A required service is unavailable. Retry later." }] }) };

test("a failed answer inside the conversation surface shows its error there and keeps focus on the button", async ({ page }, info) => {
  const modal = info.project.name === "mobile-390";
  await open(page, tokens.a);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  let surface;
  if (modal) {
    await page.getByRole("button", { name: "Conversation" }).click();
    surface = page.getByRole("dialog", { name: "Conversation" });
  } else surface = page.locator(".convo-desktop");
  await expect(surface).toBeVisible();
  await page.route("**/clarifications", (route) => route.fulfill(unavailable));
  const adopt = surface.getByRole("button", { name: "Adopt these settings" });
  await adopt.focus();
  await page.keyboard.press("Enter");
  const message = surface.locator('[role="alert"]');
  await expect(message).toContainText("unavailable"); // the error is inside the surface the person is using
  await expectInView(page, message.first(), "the error must be on screen");
  await expect(adopt).toBeFocused();
  await page.unroute("**/clarifications");
  await page.keyboard.press("Enter");
  await expect(surface.locator('[role="alert"]')).toHaveCount(0); // success clears the message
  await page.screenshot({ path: path.join(outDir, `conversation-failure-${info.project.name}.png`), fullPage: false });
});

test("a failed first submit keeps focus on the button and shows the error next to it", async ({ page }, info) => {
  await open(page, tokens.a);
  await sample(page, "Specific thesis").click();
  await page.route("**/v1/research/requests", (route) => route.request().method() === "POST" ? route.fulfill(unavailable) : route.continue());
  const prepare = page.getByRole("button", { name: "Prepare request" });
  await prepare.focus();
  await page.keyboard.press("Enter");
  await expect(alerts(page)).toContainText("unavailable");
  await expect(prepare).toBeFocused();
  await expectInView(page, alerts(page).first(), "the submit error must be on screen");
  await page.unroute("**/v1/research/requests");
  await page.keyboard.press("Enter"); // the retry works and opens the saved request
  await expect(page.getByRole("heading", { name: "Your request" })).toBeVisible();
  await page.screenshot({ path: path.join(outDir, `intake-failure-${info.project.name}.png`), fullPage: false });
});

test("a pending action shows that it is working", async ({ page }) => {
  await open(page, tokens.a);
  await sample(page, "Specific thesis").click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.route("**/clarifications", async (route) => { await new Promise((r) => setTimeout(r, 1200)); await route.continue(); });
  const adopt = page.locator("main").getByRole("button", { name: /Adopt these settings|Saving/ });
  await adopt.focus();
  await page.keyboard.press("Enter");
  await expect(adopt).toHaveAttribute("aria-disabled", "true");
  await expect(adopt).toContainText("Saving");
  const opacity = await adopt.evaluate((el) => Number(getComputedStyle(el).opacity));
  expect(opacity).toBeLessThan(1); // dimmed while busy
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await page.unroute("**/clarifications");
});

const API = process.env.P03_API_URL;

/** Another client answers the open question first, so the page's next answer is stale. */
async function answerOutOfBand(page) {
  const id = page.url().split("/research/")[1];
  const headers = { Authorization: `Bearer ${tokens.a}` };
  const bundle = await (await page.request.get(`${API}/v1/research/requests/${id}`, { headers })).json();
  const reply = await page.request.post(`${API}/v1/research/requests/${id}/clarifications`, { headers, data: {
    previous_revision_id: bundle.head.interpretation_revision_id, question_id: "adopt-suggested-settings", choice_id: "adopt" } });
  expect(reply.status()).toBe(201);
}

async function openThesis(page) {
  await open(page, tokens.a);
  await sample(page, "Specific thesis").click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
}

/** The three places a question can be answered. The sheet and the side panel exist at different widths. */
function surfaces(page, project) {
  const list = [{ name: "main", root: page.locator("main"), focus: page.locator("#state-title") }];
  if (project === "desktop") list.push({ name: "side", root: page.locator(".convo-desktop"), focus: page.locator(".convo-desktop [data-focus-target]") });
  else list.push({ name: "sheet", root: page.getByRole("dialog", { name: "Conversation" }), focus: page.locator("dialog [data-focus-target]"), open: () => page.getByRole("button", { name: "Conversation" }).click() });
  return list;
}

for (const surfaceName of ["main", "conversation"]) {
  test(`a stale answer in the ${surfaceName} surface explains itself there and moves focus into it`, async ({ page }, info) => {
    await openThesis(page);
    const surface = surfaces(page, info.project.name)[surfaceName === "main" ? 0 : 1];
    await surface.open?.();
    await answerOutOfBand(page);
    const adopt = surface.root.getByRole("button", { name: "Adopt these settings" });
    await adopt.focus();
    await page.keyboard.press("Enter");
    await expect(surface.root.locator('[role="status"]', { hasText: "changed elsewhere" })).toBeVisible(); // the form is gone; the notice still has a home
    await expect(surface.focus.first()).toBeFocused();
    await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
    await page.screenshot({ path: path.join(outDir, `stale-${surfaceName}-${info.project.name}.png`), fullPage: false });
  });

  test(`a stale answer whose reload fails says so in the ${surfaceName} surface and never claims a reload`, async ({ page }, info) => {
    await openThesis(page);
    const surface = surfaces(page, info.project.name)[surfaceName === "main" ? 0 : 1];
    await surface.open?.();
    await answerOutOfBand(page);
    await page.route("**/v1/research/requests/*", (route) => route.request().method() === "GET" ? route.fulfill(unavailable) : route.continue());
    const adopt = surface.root.getByRole("button", { name: "Adopt these settings" });
    await adopt.focus();
    await page.keyboard.press("Enter");
    const alert = surface.root.locator('[role="alert"]');
    await expect(alert).toContainText("could not be reloaded");
    await expect(surface.root.getByText("It was reloaded")).toHaveCount(0);
    await expectInView(page, alert.first(), "the reload failure must be visible where the person acted");
    await expect(adopt).toBeFocused();
    await page.unroute("**/v1/research/requests/*");
  });
}

test("a lost reply on the first submit says the request may be saved and refreshes the list", async ({ page }, info) => {
  await open(page, tokens.c); // a small list, so a new request is visible in it (the list shows at most 50)
  await expect(page.getByText("Loading saved requests.")).toHaveCount(0);
  await sample(page, /Recent rises seem to keep running/).click();
  const before = await page.locator("button.card-open").count();
  await page.route("**/v1/research/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fetch(); // the server saves the request ...
    await route.abort("failed"); // ... and the reply is lost
  });
  const prepare = page.getByRole("button", { name: "Prepare request" });
  await prepare.focus();
  await page.keyboard.press("Enter");
  await expect(alerts(page)).toContainText("may have been saved");
  await expect(prepare).toBeFocused();
  await expect.poll(() => page.locator("button.card-open").count(), { message: "the saved list must refresh" }).toBeGreaterThan(before);
  await page.unroute("**/v1/research/requests");
  await page.screenshot({ path: path.join(outDir, `lost-reply-${info.project.name}.png`), fullPage: false });
});

test("signing out and back in keeps focus on the sign-in heading and returns to Research", async ({ page }) => {
  await open(page, tokens.a);
  await page.getByRole("button", { name: "Sign out" }).click();
  const heading = page.getByRole("heading", { name: "Sign in to start" });
  await expect(heading).toBeVisible();
  await expect(heading).toBeFocused();
  const signIn = page.getByRole("button", { name: "Sign in" });
  await signIn.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
});

test("an unsent draft survives a reload and is cleared by a successful submit", async ({ page }) => {
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill("My half written hunch about volume.");
  await page.getByRole("button", { name: /Add “no leverage”/ }).click();
  await page.reload();
  await expect(page.getByLabel("Your words", { exact: true })).toHaveValue("My half written hunch about volume.");
  await expect(page.getByRole("list", { name: "Your restrictions" })).toContainText("no leverage");
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByRole("heading", { name: "Your request" })).toBeVisible();
  await page.getByRole("button", { name: "All requests" }).click();
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  await expect(page.getByLabel("Your words", { exact: true })).toHaveValue("");
});


test("a rejected session explains itself, keeps the draft for the same person and signs in again for real", async ({ page }, info) => {
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill("My careful unsent hunch.");
  await page.route("**/v1/research/requests", (route) => route.request().method() === "POST"
    ? route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ code: "auth_invalid", findings: [{ detail: "The credential is not valid for this application." }] }) })
    : route.continue());
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByRole("heading", { name: "Sign in to start" })).toBeVisible();
  const message = page.locator('[role="alert"]', { hasText: "session was rejected" });
  await expect(message).toBeVisible();
  await expect(message).toBeFocused(); // no silent drop to the page body
  await page.screenshot({ path: path.join(outDir, `session-rejected-${info.project.name}.png`), fullPage: false });
  await page.unroute("**/v1/research/requests");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible(); // a real second sign-in, not a dead loop
  await expect(page.getByLabel("Your words", { exact: true })).toHaveValue("My careful unsent hunch.");
});

test("signing out removes the draft, and another person never sees it", async ({ page }) => {
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill("Owner A private unsent hunch.");
  await page.getByRole("button", { name: /Add “no leverage”/ }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in to start" })).toBeVisible();
  const kept = await page.evaluate(() => Object.keys(window.sessionStorage).filter((k) => k.startsWith("edge-os:")));
  expect(kept, "nothing this app stored may survive a sign-out").toEqual([]);
  await page.evaluate((token) => { window.__EDGE_OS_TEST_AUTH__.getAccessToken = async () => token; }, tokens.b); // the next person signs in
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  await expect(page.getByLabel("Your words", { exact: true })).toHaveValue("");
  await expect(page.getByRole("list", { name: "Your restrictions" })).toHaveCount(0);
});

test("a failed load of a saved request keeps the retry button, focus and a visible error", async ({ page }) => {
  await open(page, tokens.c);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toBeVisible();
  await page.getByRole("button", { name: "All requests" }).click();
  await expect(page.locator("button.card-open").first()).toBeVisible();
  await page.route("**/v1/research/requests/*", (route) => route.request().method() === "GET" ? route.fulfill(unavailable) : route.continue());
  await page.locator("button.card-open").first().click();
  await expect(alerts(page)).toContainText("could not be loaded");
  const retry = page.getByRole("button", { name: "Try again" });
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Try again", exact: true })).toBeVisible(); // the second attempt has finished (and failed)
  await expect(alerts(page)).toContainText("could not be loaded"); // a second failure is still shown, never a silent state
  await expect(page.getByRole("button", { name: "Try again", exact: true })).toBeFocused();
  await page.unroute("**/v1/research/requests/*");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Your request" })).toBeVisible();
});

test("a restriction that was typed but not added is kept with the request", async ({ page }) => {
  await open(page, tokens.a);
  await sample(page, "Specific thesis").click();
  await page.getByLabel("Another restriction in your words").fill("never trade at night");
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByRole("list", { name: "Saved restrictions" })).toContainText("never trade at night");
});

test("P19 account surface keeps controls usable and meets accessibility checks", async ({ page }, info) => {
  await open(page, tokens.a);
  await page.getByRole("button", { name: "Agents" }).click();
  await expect(page.getByRole("heading", { name: "Account", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "agent-a", level: 2 })).toBeVisible();
  const agentControls = await smallControls(page);
  await page.evaluate(() => Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined))));
  const agentAxe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const agentSerious = agentAxe.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""));
  const agentContrast = await lowContrast(page);
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-p19-quality-agents.png`), fullPage: true });
  const views = page.getByRole("group", { name: "Account views" });
  await views.getByRole("button", { name: "Positions" }).focus();
  await page.keyboard.press("Enter");
  await expect(views.getByRole("button", { name: "Positions" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Position filters")).toBeVisible();
  const positionControls = await smallControls(page);
  await page.evaluate(() => Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined))));
  const positionAxe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const positionSerious = positionAxe.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""));
  const positionContrast = await lowContrast(page);
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-p19-quality-positions.png`), fullPage: true });
  await views.getByRole("button", { name: "Funds" }).click();
  const fundControls = await smallControls(page);
  await page.evaluate(() => Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined))));
  const fundAxe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const fundSerious = fundAxe.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""));
  const fundContrast = await lowContrast(page);
  await page.screenshot({ path: path.join(evidence, "screenshots", `${info.project.name}-p19-quality-funds.png`), fullPage: true });
  const evidencePath = path.join(outDir, `p19-accessibility-${info.project.name}.json`);
  const axeDetails = (items) => items.map((v) => ({ id: v.id, help: v.help,
    nodes: v.nodes.map((node) => ({ target: node.target, html: node.html, failureSummary: node.failureSummary })) }));
  const report = { agents: { small: agentControls, serious: axeDetails(agentSerious), contrast: agentContrast },
    positions: { small: positionControls, serious: axeDetails(positionSerious), contrast: positionContrast },
    funds: { small: fundControls, serious: axeDetails(fundSerious), contrast: fundContrast } };
  fs.writeFileSync(evidencePath, JSON.stringify(report, null, 2));
  expect(report.agents.small, JSON.stringify(report.agents.small)).toEqual([]);
  expect(report.positions.small, JSON.stringify(report.positions.small)).toEqual([]);
  expect(report.funds.small, JSON.stringify(report.funds.small)).toEqual([]);
  expect([...agentSerious, ...positionSerious, ...fundSerious].map((v) => ({ id: v.id, help: v.help }))).toEqual([]);
  expect([...agentContrast, ...positionContrast, ...fundContrast]).toEqual([]);
});
