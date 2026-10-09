import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";
import { expectProvenanceFits, openProvenanceAndMeasure } from "./provenance-layout.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const shots = path.join(evidence, "screenshots");
fs.mkdirSync(shots, { recursive: true });
const sample = (page, text) => page.locator("button.example", { hasText: text });
const alerts = (page) => page.locator('[role="alert"]:not(#__next-route-announcer__)');
const resultsFile = path.join(evidence, "ui-results.json");

function record(key, value) {
  const current = fs.existsSync(resultsFile) ? JSON.parse(fs.readFileSync(resultsFile, "utf8")) : {};
  current[key] = value;
  fs.writeFileSync(resultsFile, JSON.stringify(current, null, 2));
}

const THESIS = "Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. Spot only.";
const HUNCH = "Recent rises seem to keep running. Is that worth testing?";
const GROUPED_RULE = "Enter when (current quote volume is above twice its prior 10-minute mean or price is above 20) and price is above 30. Exit when the 5-minute price return is below zero.";
const GROUPED_RIGHT_RULE = "Enter when current quote volume is above twice its prior 10-minute mean or (price is above 20 and price is above 30). Exit when the 5-minute price return is below zero.";
const TINY_THRESHOLD = `-0.${"0".repeat(399)}1`;
const TINY_RULE = `Enter when the 5-minute price return is above ${TINY_THRESHOLD}. Exit when the 5-minute price return is below zero.`;
const GROUPED_ENTRY = { op: "and", args: [
  { op: "or", args: [
    { op: "gt", args: [{ op: "relative_volume", lookback_buckets: 2 }, { op: "constant", value: "2", unit: "DIMENSIONLESS" }] },
    { op: "gt", args: [{ op: "price" }, { op: "constant", value: "20", unit: "PRICE" }] },
  ] },
  { op: "gt", args: [{ op: "price" }, { op: "constant", value: "30", unit: "PRICE" }] },
] };
const GROUPED_RIGHT_ENTRY = { op: "or", args: [
  { op: "gt", args: [{ op: "relative_volume", lookback_buckets: 2 }, { op: "constant", value: "2", unit: "DIMENSIONLESS" }] },
  { op: "and", args: [
    { op: "gt", args: [{ op: "price" }, { op: "constant", value: "20", unit: "PRICE" }] },
    { op: "gt", args: [{ op: "price" }, { op: "constant", value: "30", unit: "PRICE" }] },
  ] },
] };
const TINY_ENTRY = { op: "gt", args: [{ op: "price_return", lookback_buckets: 1 },
  { op: "constant", value: TINY_THRESHOLD, unit: "DIMENSIONLESS" }] };

async function shot(page, project, name) {
  await page.screenshot({ path: path.join(shots, `${project}-${name}.png`), fullPage: true });
}

async function checkP09Interface(page) {
  return page.getByTestId("effect-comparison").evaluate((root) => {
    const parse = (value) => {
      const match = value.match(/^rgba?\(([^)]+)\)$/);
      if (match) {
        const parts = match[1].split(/[ ,/]+/).filter(Boolean).map(Number);
        return { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 };
      }
      const color = value.match(/^color\(srgb ([^)]+)\)$/);
      if (color) {
        const parts = color[1].split(/[ /]+/).filter(Boolean).map(Number);
        return { r: parts[0] * 255, g: parts[1] * 255, b: parts[2] * 255, a: parts[3] ?? 1 };
      }
      return null;
    };
    const lum = ({ r, g, b }) => {
      const channel = (value) => { value /= 255; return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    };
    const bg = (element) => {
      const layers = [];
      for (let node = element; node && node !== root.parentElement; node = node.parentElement) {
        const color = parse(getComputedStyle(node).backgroundColor);
        if (color && color.a > 0) { layers.push(color); if (color.a === 1) break; }
      }
      let base = { r: 255, g: 255, b: 255, a: 1 };
      for (const layer of layers.reverse()) base = { r: layer.r * layer.a + base.r * (1 - layer.a),
        g: layer.g * layer.a + base.g * (1 - layer.a), b: layer.b * layer.a + base.b * (1 - layer.a), a: 1 };
      return base;
    };
    const ratio = (a, b) => (Math.max(lum(a), lum(b) ) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);
    const controls = [...root.querySelectorAll('button, summary, input[type="checkbox"]')].filter((el) => {
      const style = getComputedStyle(el);
      return style.display !== "none" && style.visibility !== "hidden" && el.getBoundingClientRect().width > 0;
    });
    const sizes = controls.map((el) => {
      const box = el.matches('input[type="checkbox"]') ? el.closest("label").getBoundingClientRect() : el.getBoundingClientRect();
      return { label: (el.textContent || el.getAttribute("aria-label") || el.type || "").trim().slice(0, 48),
        width: box.width, height: box.height };
    });
    const text = [...root.querySelectorAll("p, dt, dd, label, button, summary, th, td")].filter((el) => {
      const box = el.getBoundingClientRect();
      return box.width > 0 && box.height > 0 && el.textContent.trim();
    }).map((el) => {
      const style = getComputedStyle(el), foreground = parse(style.color), background = bg(el);
      if (!foreground) return null;
      const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700);
      return { text: el.textContent.trim().slice(0, 48), ratio: foreground ? ratio(foreground, background) : 0,
        minimum: large ? 3 : 4.5 };
    }).filter((item) => item && item.ratio < item.minimum);
    return { sizes, lowContrast: text };
  });
}

async function open(page, token) {
  await injectAuth(page, token);
  await page.goto("/");
  await expect(page.getByTestId("fixture-banner")).toContainText("TEST AUTH FIXTURE");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("signed-out and rejected sessions never show data", async ({ page }, info) => {
  await injectAuth(page, tokens.bad);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in to start" })).toBeVisible();
  await expect(page.getByText("Signing in does not create a wallet")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Saved requests" })).toHaveCount(0);
  await shot(page, info.project.name, "signed-out");
});

test("empty state for an owner with no requests", async ({ page }, info) => {
  await open(page, tokens.b);
  await expect(page.getByText("Nothing saved yet.")).toBeVisible();
  await expect(page.getByTestId("moe-example")).toContainText("Imported example");
  await expect(page.getByTestId("moe-example")).toContainText("Not run by this application");
  await shot(page, info.project.name, "home-empty");
});

test("error state when saved requests cannot load", async ({ page }) => {
  await injectAuth(page, tokens.b);
  await page.route("**/v1/research/requests", (route) => route.request().method() === "GET"
    ? route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ code: "service_unavailable", findings: [{ detail: "A required service is unavailable. Retry later." }] }) })
    : route.continue());
  await page.goto("/");
  await expect(alerts(page)).toContainText("unavailable");
});

test("thesis: submit, adopt, review, save, reopen", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await sample(page, "Specific thesis").click();
  await expect(page.getByLabel("Your words", { exact: true })).toHaveValue(THESIS);
  await expect(page.getByRole("list", { name: "Your restrictions" })).toContainText("no leverage");
  await shot(page, project, "01-request-form");
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByRole("heading", { name: "Your request" })).toBeFocused();
  await expect(page.getByTestId("original-request")).toHaveText(THESIS);
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await shot(page, project, "02-needs-answer");
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await expect(page.getByTestId("rules-review")).toContainText("Enter when price rose more than 1% over the last 15 minutes");
  await expect(page.getByTestId("rules-review")).toContainText("Not granted");
  await shot(page, project, "03-review");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toBeVisible();
  await expect(page.locator("#state-title")).toBeFocused(); // the Save button is gone; focus lands on the new state
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const revisionId = (await page.getByTestId("revision-id").innerText()).trim();
  const requestUrl = page.url();
  record(`thesis-${project}`, { url: requestUrl, revisionId, original: THESIS });
  await shot(page, project, "04-saved");
  // reopen in a brand new context: nothing in this browser can supply the record
  const fresh = await page.context().browser().newContext({ viewport: page.viewportSize() });
  const again = await fresh.newPage();
  await injectAuth(again, tokens.a);
  await again.goto(requestUrl);
  await expect(again.getByTestId("revision-id")).toHaveText(revisionId);
  await expect(again.getByTestId("original-request")).toHaveText(THESIS);
  await fresh.close();
  // leaving returns focus to the opened card
  await page.getByRole("button", { name: "All requests" }).click();
  await expect(page.locator("button.card-open").first()).toBeFocused();
});

test("quote-volume rule: review, save and reopen the scheduled baseline", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await sample(page, /current quote volume is above twice its prior 10-minute mean/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await expect(page.getByTestId("rules-review")).toContainText("current quote volume divided by the mean of the previous 10 minutes is above 2");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const revisionId = (await page.getByTestId("revision-id").innerText()).trim();
  const requestUrl = page.url();
  record(`volume-rule-${project}`, { url: requestUrl, revisionId, original: "Enter when current quote volume is above twice its prior 10-minute mean; exit when the 5-minute price return is below zero." });
  const fresh = await page.context().browser().newContext({ viewport: page.viewportSize() });
  const again = await fresh.newPage();
  await injectAuth(again, tokens.a);
  await again.goto(requestUrl);
  await expect(again.getByTestId("revision-id")).toHaveText(revisionId);
  await expect(again.getByTestId("rules-review")).toContainText("previous 10 minutes");
  await fresh.close();
});

test("nested Boolean groups retain their review meaning through save", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill(GROUPED_RULE);
  await page.getByRole("radio", { name: "Specific rule or thesis" }).check();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  const expectedEntry = "Enter when (current quote volume divided by the mean of the previous 10 minutes is above 2 or price is above 20) and price is above 30";
  await expect(page.getByTestId("rules-review")).toContainText(expectedEntry);
  await shot(page, project, "grouped-rules-review");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  await expect(page.getByTestId("rules-review")).toContainText(expectedEntry);
  const revisionId = (await page.getByTestId("revision-id").innerText()).trim();
  const requestUrl = page.url();
  record(`grouped-rule-${project}`, { url: requestUrl, revisionId, original: GROUPED_RULE,
    expectedEntry, expectedEntryTree: GROUPED_ENTRY });
  await shot(page, project, "grouped-rules-saved");
});

test("a right-nested Boolean group stays distinct through save", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill(GROUPED_RIGHT_RULE);
  await page.getByRole("radio", { name: "Specific rule or thesis" }).check();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  const expectedEntry = "Enter when current quote volume divided by the mean of the previous 10 minutes is above 2 or (price is above 20 and price is above 30)";
  await expect(page.getByTestId("rules-review")).toContainText(expectedEntry);
  await shot(page, project, "grouped-right-rules-review");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  await expect(page.getByTestId("rules-review")).toContainText(expectedEntry);
  const revisionId = (await page.getByTestId("revision-id").innerText()).trim();
  record(`grouped-right-${project}`, { url: page.url(), revisionId, original: GROUPED_RIGHT_RULE,
    expectedEntry, expectedEntryTree: GROUPED_RIGHT_ENTRY });
  await shot(page, project, "grouped-right-rules-saved");
});

test("exact negative tiny threshold remains visible through save", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill(TINY_RULE);
  await page.getByRole("radio", { name: "Specific rule or thesis" }).check();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  const expectedEntry = `Enter when the 5-minute price return is above -0.${"0".repeat(397)}1%`;
  const expectedProvenance = `Enter when the 5-minute price return is above -0.${"0".repeat(397)}1%`;
  const review = page.getByTestId("rules-review");
  await expect(review).toContainText(expectedEntry);
  const width = await review.evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }));
  expect(width.scroll).toBeLessThanOrEqual(width.client);
  await shot(page, project, "tiny-threshold-review");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  await expect(review).toContainText(expectedEntry);
  const revisionId = (await page.getByTestId("revision-id").innerText()).trim();
  const requestUrl = page.url();
  record(`tiny-threshold-${project}`, { url: requestUrl, revisionId, original: TINY_RULE,
    expectedEntry, expectedProvenance, expectedEntryTree: TINY_ENTRY });
  await shot(page, project, "tiny-threshold-saved");
  const provenance = await openProvenanceAndMeasure(page, expectedProvenance);
  expectProvenanceFits(provenance);
  await shot(page, project, "tiny-threshold-provenance-open");
});

test("hunch: keyboard choice, Tab order and Escape-free completion", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  const main = page.locator("main");
  const entry = main.getByRole("radio", { name: /more than 1% over the last 15 minutes/ });
  await entry.focus();
  await page.keyboard.press("ArrowDown");
  await expect(main.getByRole("radio", { name: /more than 2% over the last 15 minutes/ })).toBeChecked();
  await page.keyboard.press("Shift+Tab"); // leaves the radio group backwards without trapping
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter"); // native form submit from the checked radio
  await expect(main.getByRole("radio", { name: /more than 2% over the last 15 minutes/ })).toHaveCount(0);
  await expect(page.locator("#state-title")).toBeFocused(); // the answered form is gone; focus lands on the new state
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await main.getByRole("button", { name: "Adopt these settings" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await expect(page.getByTestId("rules-review")).toContainText("more than 2% over the last 15 minutes");
  await shot(page, project, "05-hunch-review");
});

test("cancelling keeps the saved work and returns focus", async ({ page }) => {
  await open(page, tokens.a);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  const id = page.url().split("/research/")[1];
  await page.getByRole("button", { name: "Not now" }).first().click();
  await expect(page.locator(`#req-${id}`)).toBeFocused();
  await expect(page.locator(`#req-${id}`)).toContainText("Needs your answer");
  await page.locator(`#req-${id}`).click();
  await expect(page.getByTestId("original-request")).toContainText("Recent rises seem to keep running");
});

test("loading states are announced while the service is slow", async ({ page }) => {
  await injectAuth(page, tokens.b);
  await page.route("**/v1/research/requests", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await new Promise((resolve) => setTimeout(resolve, 1200));
    return route.continue();
  });
  await page.goto("/");
  await expect(page.getByText("Loading saved requests.")).toBeVisible();
  await expect(page.getByText("Nothing saved yet.")).toBeVisible();
});

test("no thesis stays an investigation and shows no study progress", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await sample(page, /I have no view/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNRESOLVED");
  await expect(page.getByTestId("outcome")).toContainText("No study ran");
  await expect(page.getByText("Investigate whether an effect exists").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Save this revision" })).toHaveCount(0);
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  record(`no-thesis-${project}`, { url: page.url() });
  await shot(page, project, "06-unresolved");
});

test("adopt and save a bounded pre-outcome investigation declaration", async ({ page }, info) => {
  const project = info.project.name;
  const saveAttempts = [];
  await page.route("**/v1/research/requests/*/investigations", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    saveAttempts.push(JSON.parse(route.request().postData() ?? "{}"));
    if (saveAttempts.length === 1) return route.fulfill({ status: 503, contentType: "application/json",
      body: JSON.stringify({ code: "service_unavailable", findings: [{ path: "/", detail: "Temporary fixture failure." }] }) });
    return route.continue();
  });
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill("Compare the descriptive launch cohorts in a synthetic fixture.");
  await page.getByRole("radio").nth(2).check();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("investigation-review")).toBeVisible();
  await expect(page.getByTestId("investigation-original-request")).toHaveText("Compare the descriptive launch cohorts in a synthetic fixture.");
  await expect(page.getByText(/unqualified synthetic fixture/).first()).toBeVisible();
  await expect(page.getByLabel("Unverified mechanism details and evidence gaps")).toHaveValue(/Participant identity and incentives are unverified\./);
  await expect(page.getByLabel("Outcome horizon (positive integer)")).toHaveValue("15");
  await expect(page.getByText(/Descriptive work covers the complete period without an invented holdout/)).toBeVisible();
  await page.getByRole("checkbox", { name: /I reviewed the hypothesis and every required setting/ }).check();
  const save = page.getByRole("button", { name: "Adopt and save declaration" });
  await save.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Temporary fixture failure.", { exact: true })).toBeVisible();
  await save.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("investigation-saved")).toContainText("No study started");
  await expect(page.getByRole("heading", { name: "Declaration saved" })).toBeFocused();
  await expect(page.getByTestId("investigation-saved")).toContainText("DECLARATION_SAVED");
  await expect(page.getByTestId("investigation-saved")).toContainText("P08 declaration-time outcome labels read");
  const declarationId = (await page.getByTestId("investigation-saved").locator("dd").first().innerText()).trim();
  await page.getByTestId("investigation-saved").locator("summary").click();
  const uiContent = JSON.parse(await page.getByTestId("investigation-saved").locator("details pre").innerText());
  const intakeId = page.url().split("/research/").at(-1).split("?")[0].split("#")[0];
  const exactResponse = await page.request.get(`${process.env.P03_API_URL}/v1/research/requests/${intakeId}/investigations/${declarationId}`,
    { headers: { Authorization: `Bearer ${tokens.a}` } });
  expect(exactResponse.status()).toBe(200);
  const exact = await exactResponse.json();
  expect(saveAttempts).toHaveLength(2);
  expect(saveAttempts[1]).not.toHaveProperty("fingerprint");
  expect(saveAttempts[1].operation_id).toBe(saveAttempts[0].operation_id);
  expect(saveAttempts[1].idempotency_key).toBe(saveAttempts[0].idempotency_key);
  expect(uiContent).toEqual(exact.declaration.content);
  expect(exact.access_history[0]).toMatchObject({ event: "DECLARATION_SAVED", outcome_labels_read: false,
    provider_queries: 0, study_started: false });

  await page.getByRole("button", { name: "Load explicit synthetic example" }).click();
  await expect(page.getByText(/This visible example was authored/)).toBeVisible();
  const runAdoptionText = page.getByLabel(/I reviewed these exact P08 identities/);
  await runAdoptionText.focus();
  await page.keyboard.press("Space");
  const runAdoptButton = page.getByRole("button", { name: "Adopt synthetic run declaration" });
  const beforeRun = await checkP09Interface(page);
  expect(beforeRun.sizes.every((item) => item.height >= 44), JSON.stringify(beforeRun.sizes)).toBe(true);
  expect(beforeRun.lowContrast).toEqual([]);
  const p09Checkbox = page.getByLabel(/I reviewed these exact P08 identities/);
  const p09Focus = await p09Checkbox.evaluate((el) => {
    const parse = (value) => { const match = value.match(/^rgba?\(([^)]+)\)$/); if (!match) return null;
      const parts = match[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 }; };
    const luminance = ({ r, g, b }) => { const c = (value) => { value /= 255; return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b); };
    const label = el.closest("label"), style = getComputedStyle(label);
    const ring = parse(style.outlineColor);
    let background = { r: 255, g: 255, b: 255 };
    for (let node = label; node; node = node.parentElement) {
      const color = parse(getComputedStyle(node).backgroundColor);
      if (color?.a === 1) { background = color; break; }
    }
    const ratio = ring ? (Math.max(luminance(ring), luminance(background)) + 0.05)
      / (Math.min(luminance(ring), luminance(background)) + 0.05) : 0;
    return { visible: el.matches(":focus-visible"), outline: style.outlineStyle,
      outlineWidth: parseFloat(style.outlineWidth), color: style.outlineColor, contrast: ratio };
  });
  expect(p09Focus.visible).toBe(true);
  expect(p09Focus.outline).not.toBe("none");
  expect(p09Focus.outlineWidth).toBeGreaterThanOrEqual(2);
  expect(p09Focus.contrast).toBeGreaterThanOrEqual(3);
  await runAdoptButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Run declaration saved\. No report exists yet/)).toBeVisible();
  const runPath = `${process.env.P03_API_URL}/v1/research/requests/${intakeId}/effect-runs`;
  const runsResponse = await page.request.get(runPath, { headers: { Authorization: `Bearer ${tokens.a}` } });
  expect(runsResponse.status()).toBe(200);
  const runList = await runsResponse.json();
  const exactRun = runList.runs.find((item) => item.run.p08_declaration_id === declarationId);
  expect(exactRun).toBeTruthy();
  expect(exactRun.report).toBeNull();
  expect(exactRun.events.map((event) => event.content.kind)).toEqual(["RUN_ADOPTED"]);
  const runId = exactRun.run.record_id;
  const adoptionPath = `${process.env.P03_API_URL}/v1/research/requests/${intakeId}/investigations/${declarationId}/effect-runs`;
  const adoptionReplayRequest = { ...exactRun.run.content.configuration, operation_id: crypto.randomUUID(),
    idempotency_key: `p09-repeat-${crypto.randomUUID()}` };
  const exactRepeat = await page.request.post(adoptionPath, { headers: { Authorization: `Bearer ${tokens.a}` },
    data: adoptionReplayRequest });
  expect(exactRepeat.status()).toBe(200);
  const exactRepeatBody = await exactRepeat.json();
  expect(exactRepeatBody.run.record_id).toBe(runId);
  const adoptionReplayRepeat = await page.request.post(adoptionPath, { headers: { Authorization: `Bearer ${tokens.a}` },
    data: adoptionReplayRequest });
  expect(adoptionReplayRepeat.status()).toBe(200);
  const beforeAdoptionCollision = await page.request.get(`${runPath}/${runId}`, {
    headers: { Authorization: `Bearer ${tokens.a}` } });
  const eventCountBeforeAdoptionCollision = (await beforeAdoptionCollision.json()).events.length;
  const adoptionCollision = await page.request.post(adoptionPath, { headers: { Authorization: `Bearer ${tokens.a}` },
    data: { ...adoptionReplayRequest, operation_id: crypto.randomUUID() } });
  expect(adoptionCollision.status()).toBe(409);
  const afterAdoptionCollision = await page.request.get(`${runPath}/${runId}`, {
    headers: { Authorization: `Bearer ${tokens.a}` } });
  const adoptionReplayEvents = (await afterAdoptionCollision.json()).events
    .filter((event) => event.content.kind === "RUN_ADOPTION_REPLAY");
  expect(adoptionReplayEvents).toHaveLength(1);
  expect(adoptionReplayEvents[0].content).toMatchObject({ method: "POST", path: new URL(adoptionPath).pathname,
    operation_id: adoptionReplayRequest.operation_id, idempotency_key: adoptionReplayRequest.idempotency_key,
    outcome_accessed: false });
  expect((await afterAdoptionCollision.json()).events).toHaveLength(eventCountBeforeAdoptionCollision);
  const attemptFailures = [];
  await page.route("**/effect-runs/*/attempts", async (route) => {
    attemptFailures.push({ url: route.request().url(), body: route.request().postDataJSON() });
    if (attemptFailures.length === 1) return route.fulfill({ status: 503, contentType: "application/json",
      body: JSON.stringify({ code: "service_unavailable", findings: [{ path: "/", detail: "Temporary evaluation failure. Retry the saved run." }] }) });
    const savedResponse = await route.fetch();
    expect(savedResponse.status()).toBe(201);
    return route.fulfill({ response: savedResponse, status: 503, contentType: "application/json",
      body: JSON.stringify({ code: "service_unavailable", findings: [{ path: "/", detail: "The reply was lost after the server saved the report." }] }) });
  });
  await page.getByRole("button", { name: "Evaluate synthetic fixture" }).click();
  await expect(page.getByTestId("effect-comparison").locator(".status.err")).toContainText("Temporary evaluation failure");
  await page.getByRole("button", { name: "Evaluate synthetic fixture" }).click();
  await expect(page.getByTestId("effect-report-saved")).toContainText("UNRESOLVED");
  const reportQuality = await checkP09Interface(page);
  expect(reportQuality.sizes.every((item) => item.height >= 44), JSON.stringify(reportQuality.sizes)).toBe(true);
  expect(reportQuality.lowContrast).toEqual([]);
  await expect(page.getByTestId("effect-comparison").locator(".status.err")).toContainText("reply was lost");
  await expect(page.getByText(/P09 outcome access: recorded at event sequence/)).toBeVisible();
  const reportId = (await page.getByTestId("effect-report-saved").locator("dd").first().innerText()).trim();
  const reportResponse = await page.request.get(`${runPath}/${runId}`, { headers: { Authorization: `Bearer ${tokens.a}` } });
  expect(reportResponse.status()).toBe(200);
  const exactRunAfter = await reportResponse.json();
  expect(exactRunAfter.report.record_id).toBe(reportId);
  expect(exactRunAfter.report.content.result.statistical_status).toBe("UNRESOLVED");
  expect(exactRunAfter.events.map((event) => event.content.kind)).toEqual([
    "RUN_ADOPTED", "RUN_ADOPTION_REPLAY", "ATTEMPT_STARTED", "OUTCOME_ACCESS_STARTED", "REPORT_SAVED"]);
  const primary = exactRunAfter.report.content.result.variants[0];
  expect(primary.general_comparison).toMatchObject({ triggered: { mean: "0.1" }, control: { mean: "-0.1" },
    triggered_minus_control_mean: "0.2" });
  expect(exactRunAfter.report.content.result.missing_outcome_count).toBe(4);
  const eventCountBeforeKeyCollision = exactRunAfter.events.length;
  const keyCollision = await page.request.post(`${runPath}/${runId}/attempts`, {
    headers: { Authorization: `Bearer ${tokens.a}` },
    data: { ...attemptFailures[1].body, operation_id: crypto.randomUUID() } });
  expect(keyCollision.status()).toBe(409);
  const afterKeyCollision = await page.request.get(`${runPath}/${runId}`, {
    headers: { Authorization: `Bearer ${tokens.a}` } });
  expect((await afterKeyCollision.json()).events).toHaveLength(eventCountBeforeKeyCollision);
  const reportReplayRequest = { operation_id: crypto.randomUUID(), idempotency_key: `p09-report-replay-${crypto.randomUUID()}` };
  const reportReplay = await page.request.post(`${runPath}/${runId}/attempts`, {
    headers: { Authorization: `Bearer ${tokens.a}` }, data: reportReplayRequest });
  expect(reportReplay.status()).toBe(200);
  const reportReplayBody = await reportReplay.json();
  expect(reportReplayBody.report.record_id).toBe(reportId);
  const reportReplayEventCount = reportReplayBody.events.length;
  const reportReplayRepeat = await page.request.post(`${runPath}/${runId}/attempts`, {
    headers: { Authorization: `Bearer ${tokens.a}` }, data: reportReplayRequest });
  expect(reportReplayRepeat.status()).toBe(200);
  expect((await reportReplayRepeat.json()).events).toHaveLength(reportReplayEventCount);
  const reportReplayCollision = await page.request.post(`${runPath}/${runId}/attempts`, {
    headers: { Authorization: `Bearer ${tokens.a}` },
    data: { ...reportReplayRequest, operation_id: crypto.randomUUID() } });
  expect(reportReplayCollision.status()).toBe(409);
  const afterReportReplayCollision = await page.request.get(`${runPath}/${runId}`, {
    headers: { Authorization: `Bearer ${tokens.a}` } });
  const finalReportReplayState = await afterReportReplayCollision.json();
  expect(finalReportReplayState.events).toHaveLength(reportReplayEventCount);
  const alternateConfiguration = structuredClone(exactRun.run.content.configuration);
  alternateConfiguration.bindings[0].volume_expression.args[1].value = "7";
  const alternateMapping = await page.request.post(adoptionPath, { headers: { Authorization: `Bearer ${tokens.a}` },
    data: { ...alternateConfiguration, operation_id: crypto.randomUUID(),
      idempotency_key: `p09-alternate-${crypto.randomUUID()}` } });
  expect(alternateMapping.status()).toBe(409);
  const runsAfterRejectedMapping = await page.request.get(runPath, { headers: { Authorization: `Bearer ${tokens.a}` } });
  expect((await runsAfterRejectedMapping.json()).runs).toHaveLength(1);
  await page.getByRole("button", { name: "Reopen saved report without rerunning" }).click();
  await expect(page.getByTestId("effect-report-saved")).toContainText(reportId);
  expect(attemptFailures).toHaveLength(2);
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const critical = axe.violations.filter((item) => item.impact === "serious" || item.impact === "critical");
  const qualityDir = path.join(evidence, "quality");
  fs.mkdirSync(qualityDir, { recursive: true });
  fs.writeFileSync(path.join(qualityDir, `axe-effect-comparison-${project}.json`), JSON.stringify(axe, null, 2));
  expect(critical, "P09 saved report has no serious or critical WCAG violations").toEqual([]);
  await shot(page, project, "effect-report-saved");
  await page.unroute("**/effect-runs/*/attempts");

  const requestUrl = page.url();
  record(`investigation-${project}`, { url: requestUrl, declarationId, runId, reportId,
    p09ConfigurationSha256: exactRunAfter.report.content.p09_configuration_sha256,
    fixtureSha256: exactRunAfter.report.content.fixture_sha256,
    profileSha256: exactRunAfter.report.content.profile_sha256,
    retry: { attempts: saveAttempts.length,
    reused_operation_id: saveAttempts[1].operation_id === saveAttempts[0].operation_id,
    reused_idempotency_key: saveAttempts[1].idempotency_key === saveAttempts[0].idempotency_key,
    storage_fingerprint_sent: Object.hasOwn(saveAttempts[1], "fingerprint") }, content: exact.declaration.content,
    access: Object.fromEntries(["schema_version", "event", "outcome_labels_read", "provider_queries", "study_started"]
      .map((field) => [field, exact.access_history[0][field]])),
    original: "Compare the descriptive launch cohorts in a synthetic fixture.",
    p09: { run: exactRun.run, report: exactRunAfter.report, events: finalReportReplayState.events,
      identityProof: { exactRepeatStatus: exactRepeat.status(), exactRepeatRunId: exactRepeatBody.run.record_id,
        adoptionReplayRepeatStatus: adoptionReplayRepeat.status(), adoptionChangedOperationStatus: adoptionCollision.status(),
        adoptionReceiptCount: adoptionReplayEvents.length,
        adoptionReceiptOperationId: adoptionReplayEvents[0].content.operation_id,
        adoptionReceiptKey: adoptionReplayEvents[0].content.idempotency_key,
        adoptionChangedOperationLeftEventsUnchanged:
          (await afterAdoptionCollision.json()).events.length === eventCountBeforeAdoptionCollision,
        changedOperationStatus: keyCollision.status(), changedOperationLeftEventsUnchanged:
          (await afterKeyCollision.json()).events.length === eventCountBeforeKeyCollision,
        reportReplayStatus: reportReplay.status(), reportReplayRepeatStatus: reportReplayRepeat.status(),
        reportReplayReportId: reportReplayBody.report.record_id,
        reportReplayEventCount, reportReplayReceiptKey: reportReplayRequest.idempotency_key,
        reportReplayReceiptOperationId: reportReplayRequest.operation_id,
        reportReplayChangedOperationStatus: reportReplayCollision.status(),
        reportReplayChangedOperationLeftEventsUnchanged: finalReportReplayState.events.length === reportReplayEventCount,
        finalEventKinds: finalReportReplayState.events.map((event) => event.content.kind),
        alternateMappingStatus: alternateMapping.status(), runCountAfterRejectedMapping: 1 } } });
  await shot(page, project, "investigation-saved");
  await page.getByRole("button", { name: "Reopen saved declaration" }).click();
  await expect(page.getByTestId("investigation-saved")).toContainText(declarationId);
  await expect(page.getByTestId("investigation-saved")).toContainText("No study started");
});

test("clarification refresh keeps a reviewed draft's regenerated-ID plan saveable", async ({ page }, info) => {
  const project = info.project.name;
  const proposals = [];
  const saveBodies = [];
  await page.route("**/v1/research/requests/*/investigation-proposal", async (route) => {
    const response = await route.fetch();
    const proposal = await response.json();
    proposals.push(proposal);
    return route.fulfill({ response, body: JSON.stringify(proposal) });
  });
  await page.route("**/v1/research/requests/*/investigations", async (route) => {
    if (route.request().method() === "POST") saveBodies.push(JSON.parse(route.request().postData() ?? "{}"));
    return route.continue();
  });
  await open(page, tokens.a);
  await sample(page, /I have no view/).click();
  await expect(page.getByLabel(/Use the synthetic fixture market/)).toBeChecked();
  await page.getByLabel(/Use the synthetic fixture market/).uncheck();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("investigation-review")).toBeVisible();
  const question = page.getByRole("region", { name: "What we need from you" }).locator('[data-question="choose-market"]');
  await expect(question).toBeVisible();
  await expect.poll(() => proposals.length).toBe(1);

  const initial = proposals[0];
  const intakeId = page.url().split("/research/").at(-1).split("?")[0].split("#")[0];
  const stopping = page.getByLabel("Stopping rule");
  await stopping.fill("Keep my reviewed stopping rule through clarification.");
  await expect(stopping).toHaveValue("Keep my reviewed stopping rule through clarification.");
  await question.getByRole("radio").check();
  await question.getByRole("button", { name: "Save my answer" }).click();
  await expect(page.getByText(/Your unsaved edits remain in place/)).toBeVisible();
  await expect.poll(() => proposals.length).toBe(2);
  await expect(stopping).toHaveValue("Keep my reviewed stopping rule through clarification.");
  await expect(page.getByLabel("I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.")).not.toBeChecked();

  const refreshed = proposals[1];
  expect(refreshed.interpretation_revision_id).not.toBe(initial.interpretation_revision_id);
  expect(refreshed.trial_ids).not.toEqual(initial.trial_ids);
  expect(refreshed.evaluation_ids).not.toEqual(initial.evaluation_ids);
  await page.getByLabel("I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.").check();
  await page.getByRole("button", { name: "Adopt and save declaration" }).click();
  await expect(page.getByRole("heading", { name: "Declaration saved" })).toBeFocused();
  await expect(page.getByTestId("investigation-saved")).toContainText("No study started");
  expect(saveBodies).toHaveLength(1);
  expect(saveBodies[0].expected_interpretation_revision_id).toBe(refreshed.interpretation_revision_id);
  expect(saveBodies[0].configuration.stopping_rule).toBe("Keep my reviewed stopping rule through clarification.");
  expect(saveBodies[0].trial_ids).toEqual(initial.trial_ids);
  expect(saveBodies[0].evaluation_ids).toEqual(initial.evaluation_ids);
  expect(saveBodies[0].configuration.evaluation_plan.map(({ trial_id, evaluation_id }) => [trial_id, evaluation_id]))
    .toEqual(initial.configuration.evaluation_plan.map(({ trial_id, evaluation_id }) => [trial_id, evaluation_id]));
  expect(saveBodies[0].field_origins.evaluation_plan).toMatchObject({ origin: "USER_CONFIRMED",
    source_ref: "investigation-review/2", adoption: "ADOPTED" });

  const declarationId = (await page.getByTestId("investigation-saved").locator("dd").first().innerText()).trim();
  const exactResponse = await page.request.get(`${process.env.P03_API_URL}/v1/research/requests/${intakeId}/investigations/${declarationId}`,
    { headers: { Authorization: `Bearer ${tokens.a}` } });
  expect(exactResponse.status()).toBe(200);
  const exact = await exactResponse.json();
  expect(exact.declaration.content.trial_ids).toEqual(initial.trial_ids);
  expect(exact.declaration.content.evaluation_ids).toEqual(initial.evaluation_ids);
  expect(exact.declaration.content.configuration.evaluation_plan).toEqual(saveBodies[0].configuration.evaluation_plan);
  expect(exact.declaration.content.interpretation_revision_id).toBe(refreshed.interpretation_revision_id);
  expect(exact.access_history[0]).toMatchObject({ outcome_labels_read: false, provider_queries: 0, study_started: false });
  record(`investigation-refresh-${project}`, { url: page.url(), declarationId, content: exact.declaration.content,
    access: Object.fromEntries(["schema_version", "event", "outcome_labels_read", "provider_queries", "study_started"]
      .map((field) => [field, exact.access_history[0][field]])), original: initial.configuration.question,
    identity_refresh: { trial_ids_changed_on_proposal: true, evaluation_ids_changed_on_proposal: true,
      saved_plan_retained: true, current_interpretation_saved: true } });
  await shot(page, project, "investigation-refresh-saved");
});

test("replacement retry saves one coherent new declaration after repeated proposal outages", async ({ page }, info) => {
  const project = info.project.name;
  const proposals = [];
  const replacementSaveBodies = [];
  let proposalCalls = 0;
  await page.route("**/v1/research/requests/*/investigation-proposal", async (route) => {
    proposalCalls += 1;
    if (proposalCalls === 2 || proposalCalls === 3) {
      return route.fulfill({ status: 503, contentType: "application/json",
        body: JSON.stringify({ code: "service_unavailable", findings: [{ path: "/", detail: "Temporary replacement proposal failure." }] }) });
    }
    const response = await route.fetch();
    const proposal = await response.json();
    proposals.push(proposal);
    return route.fulfill({ response, body: JSON.stringify(proposal) });
  });
  await page.route("**/v1/research/requests/*/investigations", async (route) => {
    if (route.request().method() === "POST") replacementSaveBodies.push(JSON.parse(route.request().postData() ?? "{}"));
    return route.continue();
  });

  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill("Compare the descriptive launch cohorts in a synthetic fixture.");
  await page.getByRole("radio").nth(2).check();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("investigation-review")).toBeVisible();
  await expect.poll(() => proposals.length).toBe(1);
  const originalProposal = proposals[0];
  await page.getByLabel("I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.").check();
  await page.getByRole("button", { name: "Adopt and save declaration" }).click();
  await expect(page.getByRole("heading", { name: "Declaration saved" })).toBeFocused();
  const firstDeclarationId = (await page.getByTestId("investigation-saved").locator("dd").first().innerText()).trim();
  const intakeId = page.url().split("/research/").at(-1).split("?")[0].split("#")[0];
  const auth = { headers: { Authorization: `Bearer ${tokens.a}` } };
  const firstRead = await page.request.get(`${process.env.P03_API_URL}/v1/research/requests/${intakeId}/investigations/${firstDeclarationId}`, auth);
  expect(firstRead.status()).toBe(200);
  const firstSaved = await firstRead.json();

  await page.getByRole("button", { name: "Review another hypothesis" }).click();
  const replacementError = page.getByTestId("investigation-review").locator(".status.err").first();
  await expect(replacementError).toContainText("Temporary replacement proposal failure.");
  await expect(page.getByRole("button", { name: "Retry new hypothesis" })).toBeVisible();
  await expect(replacementError).toContainText("The saved declaration is unchanged.");
  await page.getByRole("button", { name: "Retry new hypothesis" }).click();
  await expect(replacementError).toContainText("Temporary replacement proposal failure.");
  await expect(page.getByRole("button", { name: "Retry new hypothesis" })).toBeVisible();
  await page.getByRole("button", { name: "Retry new hypothesis" }).click();
  await expect.poll(() => proposals.length).toBe(2);
  await expect(page.getByTestId("investigation-original-request")).toHaveText("Compare the descriptive launch cohorts in a synthetic fixture.");
  await expect(page.getByText(/request interpretation changed/i)).toHaveCount(0);
  const replacementProposal = proposals[1];
  expect(replacementProposal.edge_spec.edge_id).not.toBe(originalProposal.edge_spec.edge_id);
  expect(replacementProposal.trial_ids).not.toEqual(originalProposal.trial_ids);
  expect(replacementProposal.evaluation_ids).not.toEqual(originalProposal.evaluation_ids);
  await page.getByLabel("I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.").check();
  await page.getByRole("button", { name: "Adopt and save declaration" }).click();
  await expect(page.getByRole("heading", { name: "Declaration saved" })).toBeFocused();
  expect(replacementSaveBodies).toHaveLength(2);
  const newSave = replacementSaveBodies[1];
  expect(newSave.edge_spec.edge_id).toBe(replacementProposal.edge_spec.edge_id);
  expect(newSave.trial_ids).toEqual(replacementProposal.trial_ids);
  expect(newSave.evaluation_ids).toEqual(replacementProposal.evaluation_ids);
  expect(newSave.configuration.evaluation_plan).toEqual(replacementProposal.configuration.evaluation_plan);
  const secondDeclarationId = (await page.getByTestId("investigation-saved").locator("dd").first().innerText()).trim();
  expect(secondDeclarationId).not.toBe(firstDeclarationId);
  const secondRead = await page.request.get(`${process.env.P03_API_URL}/v1/research/requests/${intakeId}/investigations/${secondDeclarationId}`, auth);
  expect(secondRead.status()).toBe(200);
  const secondSaved = await secondRead.json();
  expect(secondSaved.declaration.content.edge_spec.edge_id).toBe(replacementProposal.edge_spec.edge_id);
  expect(secondSaved.declaration.content.configuration.evaluation_plan).toEqual(replacementProposal.configuration.evaluation_plan);
  expect(secondSaved.access_history[0]).toMatchObject({ outcome_labels_read: false, provider_queries: 0, study_started: false });
  const oldReadAfterSave = await page.request.get(`${process.env.P03_API_URL}/v1/research/requests/${intakeId}/investigations/${firstDeclarationId}`, auth);
  expect(oldReadAfterSave.status()).toBe(200);
  expect((await oldReadAfterSave.json()).declaration.content).toEqual(firstSaved.declaration.content);
  const reopenButtons = page.getByRole("button", { name: "Reopen saved declaration" });
  await reopenButtons.first().click();
  await expect(page.getByTestId("investigation-saved")).toContainText(firstDeclarationId);
  await reopenButtons.nth(1).click();
  await expect(page.getByTestId("investigation-saved")).toContainText(secondDeclarationId);
  record(`investigation-replacement-retry-${project}`, { url: page.url(), declarationId: secondDeclarationId,
    content: secondSaved.declaration.content,
    access: Object.fromEntries(["schema_version", "event", "outcome_labels_read", "provider_queries", "study_started"]
      .map((field) => [field, secondSaved.access_history[0][field]])), original: "Compare the descriptive launch cohorts in a synthetic fixture.",
    firstDeclarationId, secondDeclarationId,
    proposalCalls, failedReplacementAttempts: 2, replacementEdgeChanged: true,
    savedEdgeId: secondSaved.declaration.content.edge_spec.edge_id,
    savedTrialIds: secondSaved.declaration.content.trial_ids,
    savedEvaluationIds: secondSaved.declaration.content.evaluation_ids,
    savedPlan: secondSaved.declaration.content.configuration.evaluation_plan,
    firstDeclarationUnchanged: true, reopenedBothDeclarations: true });
  await shot(page, project, "investigation-replacement-retry-saved");
});

test("unsupported meaning and unsupported restriction are kept and block compilation", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await sample(page, /Tokens launched in the last 24 hours/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNSUPPORTED");
  await expect(page.getByTestId("original-request")).toContainText("Tokens launched in the last 24 hours");
  await shot(page, project, "07-unsupported-meaning");
  await page.getByRole("button", { name: "All requests" }).click();
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  await page.getByLabel("Your words", { exact: true }).fill(HUNCH);
  await page.getByLabel("Another restriction in your words").fill("only tokens younger than 24 hours");
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNSUPPORTED");
  await expect(page.getByRole("list", { name: "Saved restrictions" })).toContainText("only tokens younger than 24 hours");

  await open(page, tokens.a);
  await sample(page, /14-period RSI is above 70/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "UNSUPPORTED");
  await expect(page.getByTestId("outcome")).toContainText("Entry rule:");
  await expect(page.getByTestId("outcome")).toContainText("rsi");
});

test("unscripted text is a system message, not a verdict on the idea", async ({ page }) => {
  await open(page, tokens.a);
  await page.getByLabel("Your words", { exact: true }).fill("Something nobody scripted.");
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "INVALID_INPUT");
  await expect(page.getByTestId("outcome")).toContainText("not a verdict on the idea");
});

test("another owner cannot open the record", async ({ page }) => {
  const results = JSON.parse(fs.readFileSync(resultsFile, "utf8"));
  const url = Object.values(results).find((r) => r.url?.includes("#/research/")).url;
  await injectAuth(page, tokens.b);
  await page.goto(url);
  await expect(alerts(page)).toContainText("not found");
  await expect(page.getByTestId("original-request")).toHaveCount(0);
});

test("conversation: same record, focus handling, Escape and Tab containment", async ({ page }, info) => {
  const project = info.project.name;
  await open(page, tokens.a);
  await sample(page, /Recent rises seem to keep running/).click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
  if (project === "mobile-390") {
    const trigger = page.getByRole("button", { name: "Conversation" });
    await trigger.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Conversation" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Recent rises seem to keep running");
    await shot(page, project, "08-conversation-sheet");
    for (let i = 0; i < 14; i++) {
      await page.keyboard.press("Tab");
      expect(await page.evaluate(() => !!document.activeElement?.closest("dialog"))).toBe(true);
    }
    for (let i = 0; i < 14; i++) {
      await page.keyboard.press("Shift+Tab");
      expect(await page.evaluate(() => !!document.activeElement?.closest("dialog"))).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  } else {
    const side = page.locator(".convo-desktop");
    await expect(side).toContainText("Recent rises seem to keep running");
    await side.getByRole("radio", { name: /more than 3% over the last 30 minutes/ }).check();
    await side.getByRole("button", { name: "Save my answer" }).click();
    await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "NEEDS_CLARIFICATION");
    await expect(side.getByRole("log")).toContainText("Question");
    await expect(side.getByRole("log")).toContainText("Entry rule: Enter when price rose more than 3% over the last 30 minutes");
    await expect(side.getByRole("log")).not.toContainText("g6-3pct");
    await shot(page, project, "08-conversation-panel");
  }
});

test("sections other than Research say what is unavailable", async ({ page }) => {
  await open(page, tokens.a);
  await page.getByRole("button", { name: "Funds" }).click();
  await expect(page.getByText("Not available in this build")).toBeVisible();
  await page.getByRole("button", { name: "Research" }).click();
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
});
