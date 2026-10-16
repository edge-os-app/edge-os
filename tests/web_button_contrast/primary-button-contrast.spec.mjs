import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Real production stylesheets, in the order apps/web/app/layout.tsx imports them.
const appDir = fileURLToPath(new URL("../../apps/web/app/", import.meta.url));
const organicCss = readFileSync(`${appDir}organic.css`, "utf8");
const appCss = readFileSync(`${appDir}app.css`, "utf8");

const MIN_CONTRAST = 4.5; // P03 serious-axe rule for enabled ordinary-size text.
const MAX_FRAMES = 600;

const fixture = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Primary button contrast</title>
<style>${organicCss}</style><style>${appCss}</style></head>
<body><main class="btn-row">
<button id="target" class="btn btn-primary" type="button">Start investigation job</button>
<button id="other" class="btn btn-secondary" type="button">Check job status</button>
</main></body></html>`;

function parseColor(value) {
  let m = value.match(/^rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)$/);
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  m = value.match(/^color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+))?\)$/);
  if (m) return { r: +m[1] * 255, g: +m[2] * 255, b: +m[3] * 255, a: m[4] === undefined ? 1 : +m[4] };
  throw new Error(`unsupported computed color: ${value}`);
}

function over(top, bottom) {
  const a = top.a + bottom.a * (1 - top.a);
  const mix = (t, b) => (t * top.a + b * bottom.a * (1 - top.a)) / a;
  return { r: mix(top.r, bottom.r), g: mix(top.g, bottom.g), b: mix(top.b, bottom.b), a };
}

function luminance({ r, g, b }) {
  const lin = (c) => { const s = c / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(sample) {
  const page = parseColor(sample.pageBg);
  const bg = over(parseColor(sample.bg), page);
  const fg = over(parseColor(sample.fg), bg);
  const [hi, lo] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// Runs `action` inside the page, then reads the rendered state at once and on every animation
// frame until no transition is running on the button. The first sample is taken in the same task
// as the state change, so it holds the transition's starting colour.
async function sampleThrough(page, action) {
  return page.evaluate(({ action, maxFrames }) => new Promise((resolve, reject) => {
    const btn = document.getElementById("target");
    const pageBg = getComputedStyle(document.body).backgroundColor;
    if (action === "disable") btn.disabled = true;
    if (action === "enable") btn.disabled = false;
    const samples = [];
    let frames = 0;
    const read = () => {
      const cs = getComputedStyle(btn);
      samples.push({ frame: frames, bg: cs.backgroundColor, fg: cs.color, opacity: cs.opacity, pageBg,
        disabled: btn.matches(":disabled"), hovered: btn.matches(":hover"), active: btn.matches(":active") });
    };
    read();
    const tick = () => {
      frames += 1;
      read();
      const running = btn.getAnimations().some((a) => a.playState !== "finished" && a.playState !== "idle");
      if (!running && frames >= 2) resolve(samples);
      else if (frames > maxFrames) reject(new Error("button transition did not settle"));
      else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }), { action, maxFrames: MAX_FRAMES });
}

function expectEnabledSamplesReadable(samples, label) {
  const enabled = samples.filter((s) => !s.disabled);
  expect(enabled.length, `${label}: enabled samples`).toBeGreaterThan(0);
  const measured = enabled.map((s) => ({ ...s, contrast: Number(contrast(s).toFixed(2)) }));
  const worst = measured.reduce((a, b) => (b.contrast < a.contrast ? b : a));
  for (const s of measured) expect(s.opacity, `${label}: enabled opacity`).toBe("1");
  expect(worst.contrast, `${label}: worst enabled sample ${JSON.stringify(worst)}`).toBeGreaterThanOrEqual(MIN_CONTRAST);
  return measured;
}

async function record(testInfo, name, data) {
  await testInfo.attach(name, { body: JSON.stringify(data, null, 2), contentType: "application/json" });
}

async function hoverTarget(page) {
  await page.locator("#target").hover();
  await expect.poll(() => page.locator("#target").evaluate((b) => b.matches(":hover"))).toBe(true);
}

test.beforeEach(async ({ page }, testInfo) => {
  await page.setContent(fixture);
  const hoverNone = await page.evaluate(() => matchMedia("(hover: none)").matches);
  expect(hoverNone, "project hover capability").toBe(testInfo.project.name.includes("hover-none"));
});

test("rest state and keyboard focus keep readable text and a visible focus ring", async ({ page }, testInfo) => {
  await page.keyboard.press("Tab");
  const target = page.locator("#target");
  await expect(target).toBeFocused();
  const ring = await target.evaluate((b) => ({ focusVisible: b.matches(":focus-visible"), style: getComputedStyle(b).outlineStyle, width: getComputedStyle(b).outlineWidth }));
  expect(ring.focusVisible).toBe(true);
  expect(ring.style).not.toBe("none");
  expect(parseFloat(ring.width)).toBeGreaterThan(0);
  const samples = expectEnabledSamplesReadable(await sampleThrough(page, "none"), "rest");
  await record(testInfo, "rest-focus", { ring, samples });
});

test("normal hover and active transitions keep readable text on every frame", async ({ page }, testInfo) => {
  await hoverTarget(page);
  const hover = expectEnabledSamplesReadable(await sampleThrough(page, "none"), "hover");
  await page.mouse.down();
  const active = expectEnabledSamplesReadable(await sampleThrough(page, "none"), "active");
  expect(active.some((s) => s.active)).toBe(true);
  await page.mouse.up();
  const release = expectEnabledSamplesReadable(await sampleThrough(page, "none"), "release");
  await record(testInfo, "hover-active", { hover, active, release });
});

test("busy disabled state under the pointer re-enables with readable text throughout default motion", async ({ page }, testInfo) => {
  const transition = await page.locator("#target").evaluate((b) => getComputedStyle(b).transitionDuration);
  expect(transition, "default motion keeps the button transition").not.toMatch(/^0s(, 0s)*$/);
  await hoverTarget(page);
  const before = expectEnabledSamplesReadable(await sampleThrough(page, "none"), "hover before busy");

  const busy = await sampleThrough(page, "disable");
  const settledBusy = busy.at(-1);
  expect(settledBusy.disabled && settledBusy.hovered, "busy state is disabled under the pointer").toBe(true);
  const clicks = await page.evaluate(() => {
    const btn = document.getElementById("target");
    let count = 0;
    btn.addEventListener("click", () => { count += 1; });
    btn.click();
    return count;
  });
  expect(clicks, "disabled button ignores activation").toBe(0);

  const reenabled = await sampleThrough(page, "enable");
  expect(reenabled[0].hovered, "pointer still over the button at re-enable").toBe(true);
  const measured = expectEnabledSamplesReadable(reenabled, "re-enabled under pointer");
  await record(testInfo, "busy-cycle", { transition, before, busy, reenabled: measured });

  const axe = await new AxeBuilder({ page }).include("#target").withRules(["color-contrast"]).analyze();
  expect(axe.violations, "settled axe color-contrast").toEqual([]);
});

test("reduced motion removes the transition and keeps the busy cycle readable", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const transition = await page.locator("#target").evaluate((b) => getComputedStyle(b).transitionDuration);
  expect(transition).toMatch(/^0s(, 0s)*$/);
  await hoverTarget(page);
  await sampleThrough(page, "disable");
  const reenabled = await sampleThrough(page, "enable");
  const measured = expectEnabledSamplesReadable(reenabled, "reduced-motion re-enable");
  await record(testInfo, "reduced-motion", { transition, reenabled: measured });
});
