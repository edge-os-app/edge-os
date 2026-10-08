import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

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

async function shot(page, project, name) {
  await page.screenshot({ path: path.join(shots, `${project}-${name}.png`), fullPage: true });
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
  await expect(page.getByTestId("moe-example")).toContainText("Imported example · not run by this application");
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
