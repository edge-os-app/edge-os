/** After an API and worker restart, the saved financial journey reopens unchanged in a new browser context. */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { injectAuth, tokens } from "./fixture-auth.mjs";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";
const financialFile = path.join(evidence, "financial-results.json");

test("restarted services reopen the confirmed and the reconciled original actions", async ({ page }, info) => {
  const project = info.project.name;
  const saved = JSON.parse(fs.readFileSync(financialFile, "utf8"));
  await injectAuth(page, tokens.a);
  for (const [key, receipts] of [[`main-${project}`, "CONFIRMED"], [`lost-ack-${project}`, "SUBMISSION_UNKNOWN → CONFIRMED"]]) {
    const { agentId } = saved[key];
    await page.goto(`/#/positions?agent=${encodeURIComponent(agentId)}`);
    const actions = page.getByRole("region", { name: "Agent actions" });
    await expect(actions.getByTestId("actions-jobs")).toContainText("SUBMITTED_CONFIRMED");
    await actions.getByRole("button", { name: /Open action/ }).first().click();
    await expect(actions.getByTestId("action-receipts")).toHaveText(receipts);
  }
  const stop = saved[`stop-${project}`];
  await page.goto(`/#/positions?agent=${encodeURIComponent(stop.agentId)}`);
  await expect(page.getByRole("region", { name: "Agent actions" }).getByTestId("actions-stops")).toContainText("HALT_ALL_SWAPS");
});
