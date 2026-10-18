import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";
import { noSidewaysScroll } from "./research-flow.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
fs.mkdirSync(shots, { recursive: true });
const shot = (page, project, name) => page.screenshot({ path: path.join(shots, `${project}-landing-${name}.png`), fullPage: true });

test.describe.configure({ mode: "serial" });

test("landing at / renders without starting sign-in and records the network it used", async ({ page }, info) => {
  const requests = [];
  page.on("request", (request) => requests.push(request.url()));
  const chunks = [];
  page.on("response", (response) => { if (response.url().endsWith(".js")) chunks.push(response); });
  // A fixture session is injected on purpose: the landing must ignore it.
  await injectAuth(page, tokens.a);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: /Test your trade idea/ })).toBeVisible();
  await expect(page.getByTestId("fixture-banner")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Sign in to start" })).toHaveCount(0);
  await page.waitForLoadState("networkidle");
  const apiCalls = requests.filter((url) => url.includes("/v1/"));
  expect(apiCalls).toEqual([]);
  const scripts = await Promise.all(chunks.map(async (response) => ({ url: response.url(), privy: /privy/i.test(await response.text().catch(() => "")) })));
  fs.writeFileSync(path.join(evidence, `landing-network-${info.project.name}.json`), JSON.stringify({
    requestCount: requests.length, apiCalls, scriptCount: scripts.length, scriptsMentioningPrivy: scripts.filter((s) => s.privy).map((s) => s.url),
  }, null, 2));
  await noSidewaysScroll(page);
  await shot(page, info.project.name, "root");
});

test("skip link is first in tab order and focus is visible", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  expect((await skip.boundingBox()).x).toBeGreaterThanOrEqual(0);
  await skip.press("Enter");
  await expect(page).toHaveURL(/#main$/);
  const enter = page.getByRole("banner").getByRole("link", { name: "Enter app" });
  await enter.focus();
  await expect(enter).toBeFocused();
  const outline = await enter.evaluate((el) => { const style = getComputedStyle(el); return { width: style.outlineWidth, style: style.outlineStyle }; });
  expect(outline).toEqual({ width: "3px", style: "solid" });
});

test("Enter app opens the existing app at /app with a fixture session, then research navigation and reload work under /app#/", async ({ page }, info) => {
  await injectAuth(page, tokens.a);
  await page.goto("/");
  await page.getByRole("banner").getByRole("link", { name: "Enter app" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByTestId("fixture-banner")).toContainText("TEST AUTH FIXTURE");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  await shot(page, info.project.name, "app");

  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Agents" }).click();
  await expect(page).toHaveURL(/\/app#\/agents$/);
  await page.reload();
  await expect(page).toHaveURL(/\/app#\/agents$/);
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Agents" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("fixture-banner")).toContainText("TEST AUTH FIXTURE");

  await page.goto("/app#/research");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
});

test("content is fully visible without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL: test.info().project.use.baseURL });
  const page = await context.newPage();
  await page.goto("/");
  for (const name of ["Ask, check, then go live.", "Answers to the real worries.", "Built on Monad", "An edge needs a reason, not a lucky chart."]) {
    await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  }
  const hidden = await page.locator("[data-reveal]").evaluateAll((blocks) => blocks.filter((block) => getComputedStyle(block).opacity !== "1").length);
  expect(hidden).toBe(0);
  await context.close();
});

test("reduced motion shows everything and plays no animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const state = await page.evaluate(() => ({
    running: document.getAnimations().filter((animation) => animation.playState === "running").length,
    hidden: [...document.querySelectorAll("[data-reveal]")].filter((block) => getComputedStyle(block).opacity !== "1").length,
    smooth: getComputedStyle(document.documentElement).scrollBehavior,
  }));
  expect(state).toEqual({ running: 0, hidden: 0, smooth: "auto" });
});

test("with motion allowed, blocks below the fold fade in as they scroll into view", async ({ page }) => {
  await page.goto("/");
  const closing = page.locator(".lp-closing-card");
  await closing.scrollIntoViewIfNeeded();
  await expect.poll(() => closing.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
});

// WCAG 2.x contrast from the real computed colors, unrounded: 4.4999 must fail.
const channel = (value) => { const v = value / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
const luminance = ([r, g, b]) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
const rgbOf = (css) => css.match(/[\d.]+/g).slice(0, 3).map(Number);
const contrastOf = (style) => { const [hi, lo] = [luminance(rgbOf(style.color)), luminance(rgbOf(style.backgroundColor))].sort((a, b) => b - a); return (hi + 0.05) / (lo + 0.05); };
const readStyle = (button) => button.evaluate((el) => { const s = getComputedStyle(el); return { color: s.color, backgroundColor: s.backgroundColor, fontSize: s.fontSize }; });

test("every primary button keeps text contrast of at least 4.5:1 at rest, on hover and on keyboard focus", async ({ page }) => {
  await page.goto("/");
  const buttons = page.locator(".lp-btn-primary");
  expect(await buttons.count()).toBe(3);
  for (let index = 0; index < 3; index += 1) {
    const button = buttons.nth(index);
    await button.scrollIntoViewIfNeeded();
    await page.mouse.move(0, 0);
    const rest = await readStyle(button);
    await button.hover();
    const hover = await readStyle(button);
    await page.mouse.move(0, 0);
    await page.keyboard.press("Tab");
    await button.focus();
    const focus = await readStyle(button);
    const label = `primary button ${index} (${rest.fontSize})`;
    expect(contrastOf(rest), `${label} at rest`).toBeGreaterThanOrEqual(4.5);
    expect(contrastOf(hover), `${label} on hover`).toBeGreaterThanOrEqual(4.5);
    expect(contrastOf(focus), `${label} on focus`).toBeGreaterThanOrEqual(4.5);
    expect(hover.backgroundColor, `${label} hover differs from rest`).not.toBe(rest.backgroundColor);
  }
});

// The round stamp must not cover any lettering of the compact slip header. The stamp is a circle, so the check uses the real rendered
// circle (center of its box, half its width) against the real text rectangles, not the larger box of the rotated square.
const circleHitsRect = (circle, rect) => {
  const nearestX = Math.max(rect.left, Math.min(circle.x, rect.right));
  const nearestY = Math.max(rect.top, Math.min(circle.y, rect.bottom));
  return Math.hypot(circle.x - nearestX, circle.y - nearestY) < circle.r;
};

test("the compact slip stamp covers neither the title nor the Illustrative label at 1280, 924 and 390 px", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one pass sets all three widths itself");
  for (const width of [1280, 924, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    const slip = page.locator(".lp-slip-compact");
    await slip.scrollIntoViewIfNeeded();
    await expect(slip).toHaveCSS("opacity", "1");
    await page.waitForTimeout(900);
    const geometry = await page.evaluate(() => {
      const box = (el) => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; };
      const stamp = document.querySelector(".lp-stamp-small");
      const s = stamp.getBoundingClientRect();
      const label = document.querySelector(".lp-slip-compact .lp-slip-meta");
      const range = document.createRange(); range.selectNodeContents(label);
      return { circle: { x: s.left + s.width / 2, y: s.top + s.height / 2, r: stamp.offsetWidth / 2 },
        label: box(label), labelText: label.textContent, labelLines: range.getClientRects().length,
        title: box(document.querySelector(".lp-slip-compact .lp-slip-title")) };
    });
    expect(geometry.labelText, `${width}px label text`).toContain("Illustrative");
    expect(circleHitsRect(geometry.circle, geometry.label), `${width}px: stamp covers the Illustrative label`).toBe(false);
    expect(circleHitsRect(geometry.circle, geometry.title), `${width}px: stamp covers the slip title`).toBe(false);
  }
});
