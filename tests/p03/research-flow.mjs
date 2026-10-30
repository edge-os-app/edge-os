/**
 * Shared steps for the #58 recorded-history research journey specs. Every source is a SYNTHETIC recorded-response
 * bundle served by the isolated test API; nothing reaches a provider, a model or a wallet.
 */
import { expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { injectAuth } from "./fixture-auth.mjs";

export const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
export const api = process.env.P03_API_URL;
const shots = path.join(evidence, "screenshots");
const resultsFile = path.join(evidence, "research-results.json");

export const sample = (page, text) => page.locator("button.example", { hasText: text });

export function record(key, value) {
  const saved = fs.existsSync(resultsFile) ? JSON.parse(fs.readFileSync(resultsFile, "utf8")) : {};
  saved[key] = { ...(saved[key] ?? {}), ...value };
  fs.writeFileSync(resultsFile, JSON.stringify(saved, null, 2));
}

export function saved(key) {
  return JSON.parse(fs.readFileSync(resultsFile, "utf8"))[key];
}

export async function shot(page, project, name) {
  fs.mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, `${project}-rg-${name}.png`), fullPage: true });
}

export async function open(page, token) {
  await injectAuth(page, token);
  await page.goto("/app");
  await expect(page.getByTestId("fixture-banner")).toContainText("TEST AUTH FIXTURE");
}

export async function noSidewaysScroll(page) {
  const found = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const all = [...document.querySelectorAll("body *")];
    const widest = all.map((el) => ({ el, right: el.getBoundingClientRect().right }))
      .filter((item) => item.right > width + 1).sort((a, b) => b.right - a.right)[0];
    const inner = all.filter((el) => el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX === "visible")
      .map((el) => `${el.tagName.toLowerCase()}.${el.className}:${el.scrollWidth}>${el.clientWidth}:${(el.textContent ?? "").slice(0, 40)}`);
    return { overflow: document.documentElement.scrollWidth - width,
      widest: widest ? `${widest.el.tagName.toLowerCase()}:${(widest.el.textContent ?? "").slice(0, 60)}` : inner.slice(-3).join(" | ") };
  });
  expect(found.overflow, `sideways scroll caused by ${found.widest}`).toBeLessThanOrEqual(0);
}

export async function noSeriousAxe(page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
}

export async function apiGet(page, token, route) {
  const response = await page.request.get(`${api}${route}`, { headers: { Authorization: `Bearer ${token}` } });
  return { status: response.status(), body: await response.json().catch(() => ({})) };
}

export async function apiPost(page, token, route, data) {
  const response = await page.request.post(`${api}${route}`, { headers: { Authorization: `Bearer ${token}` }, data });
  return { status: response.status(), body: await response.json().catch(() => ({})) };
}

/** Open the saved investigation request and its history section. */
export async function historySection(page, url) {
  await page.goto(url);
  const section = page.getByTestId("history-investigation");
  await expect(section).toBeVisible();
  return section;
}

/** Fill and adopt one recorded-history declaration entirely through the screen. */
export async function declare(section, { source, hypothesis, direction = "OUTPERFORM", rules, providerRequests = "2" }) {
  const form = section.locator("details").filter({ hasText: "Declare a new recorded-history investigation" });
  if (!(await form.evaluate((node) => node.open))) await form.locator("summary").click();
  await form.getByLabel("Recorded source").selectOption({ label: source });
  await form.getByLabel("Your hypothesis in your own words").fill(hypothesis);
  await form.getByLabel("What you will check").selectOption(direction);
  for (const [index, rule] of rules.entries()) {
    if (index > 0) await form.getByRole("button", { name: "Add another rule" }).click();
    await form.getByLabel(`Rule ${index + 1} lookback buckets`).fill(rule.lookback);
    await form.getByLabel(`Rule ${index + 1} return condition`).selectOption(rule.rise ?? "gt");
    await form.getByLabel(`Rule ${index + 1} return threshold`).fill(rule.threshold);
    await form.getByLabel(`Rule ${index + 1} volume threshold`).fill(rule.volume);
  }
  // An operating-release source fixes its bounds; the field is read-only there (pass null).
  if (providerRequests !== null) await form.getByLabel("Bound provider_requests").fill(providerRequests);
  await form.getByLabel("I reviewed and adopt every setting above before any data is read").check();
  await form.getByRole("button", { name: "Save history declaration" }).click();
  await expect(section.getByText("Declaration saved before any collection. No data was read.")).toBeVisible();
  return (await section.getByTestId("history-declaration-id").innerText()).trim();
}

export async function openDeclaration(section, hypothesis) {
  await section.locator(".card").filter({ hasText: hypothesis }).getByRole("button", { name: "Open this declaration" }).click();
  await expect(section.getByTestId("history-declaration")).toBeVisible();
}

export async function jobsFor(page, token, intakeId, declarationId) {
  const { body } = await apiGet(page, token, `/v1/research/requests/${intakeId}/history-investigations/${declarationId}/jobs`);
  return body.jobs;
}
