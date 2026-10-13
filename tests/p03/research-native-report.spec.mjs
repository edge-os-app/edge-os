/**
 * #58 SOURCE-LOCAL, phase 2, after one research worker pass: the native job's saved dataset and report, the transport
 * facts it computed apart from the recording's declarations, market adoption as a NEW draft, publication and a
 * labelled replay with simulated fills. Another owner cannot read the dataset. SYNTHETIC recordings only.
 */
import { test, expect } from "@playwright/test";
import { tokens } from "./fixture-auth.mjs";
import { apiGet, historySection, noSeriousAxe, noSidewaysScroll, open, openDeclaration, record, sample, saved,
  shot } from "./research-flow.mjs";

const ownerToken = (project) => process.env[`P03_TOKEN_NATIVE_${project.replace("-", "_").toUpperCase()}`];

test("native report, transport facts, market adoption, publication and labelled replay", async ({ page }, info) => {
  const project = info.project.name;
  const token = ownerToken(project);
  const run = saved(`native-${project}`);
  await open(page, token);
  const section = await historySection(page, run.url);
  await openDeclaration(section, run.hypothesis);
  const job = section.getByTestId("history-job").first();
  await expect(job).toHaveAttribute("data-state", "REPORTED");
  const facts = job.getByTestId("history-transport");
  await expect(facts).toContainText("2 Envio pages framed");
  await expect(facts).toContainText("chain id checked against recorded responses: 143 (MONAD)");
  await expect(facts).toContainText("receipt corroboration COMPLETE, 24 of 24 checked, 0 mismatches");
  await expect(facts).toContainText("ENVIO_HYPERSYNC 2, QUICKNODE_JSON_RPC 25");
  await expect(facts).toContainText("Recorded declarations, not read by the application");
  await expect(job).toContainText("provider usage MEASURED_CLIENT_CALLS");
  const report = job.getByTestId("history-report");
  await expect(report).toContainText("RECORDED_NATIVE_RESPONSE; SYNTHETIC_FIXTURE; verdict QUALIFIED");
  const datasetId = (await report.getByTestId("history-report-dataset").innerText()).trim();
  await shot(page, project, "n2-native-report");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);

  // Another owner cannot read the native dataset or its job.
  expect((await apiGet(page, tokens.b, `/v1/research/history-datasets/${datasetId}`)).status).toBe(404);

  // A strategy request on the same owner: save the fixture-market revision, then adopt the native market.
  await page.goto("/");
  await sample(page, "Specific thesis").click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const fixtureRevision = (await page.getByTestId("revision-id").innerText()).trim();
  const adoption = page.getByTestId("market-adoption");
  await adoption.getByLabel("Saved dataset").selectOption(datasetId);
  const reviewBox = adoption.getByTestId("market-adoption-review");
  await expect(reviewBox).toContainText("0x" + "d1".repeat(20));
  await expect(reviewBox).toContainText("QUOTE:0x" + "d2".repeat(20));
  await expect(reviewBox).toContainText("RECORDED_NATIVE_RESPONSE");
  await adoption.getByLabel("Trade size in the new quote unit").fill("50");
  await adoption.getByLabel("Largest position value in the new quote unit").fill("50");
  const declaredRule = (await apiGet(page, token, "/v1/research/history-datasets")).body.datasets
    .find((item) => item.dataset_id === datasetId).declared_rules[0];
  await adoption.getByLabel("Entry rule (one you declared for this dataset)").selectOption(declaredRule.evaluation_id);
  await adoption.getByLabel("Exit lookback (buckets)").fill("2");
  await adoption.getByLabel("Exit threshold (fraction, for example -0.001)").fill("-0.001");
  await adoption.getByRole("checkbox").check();
  await adoption.getByRole("button", { name: "Adopt this market for a new draft" }).click();
  await expect(adoption.getByRole("status")).toContainText("uses the recorded market");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const nativeRevision = (await page.getByTestId("revision-id").innerText()).trim();
  expect(nativeRevision).not.toBe(fixtureRevision);

  const replay = page.getByTestId("spot-replay");
  await replay.getByLabel("Price data").selectOption(datasetId);
  await expect(replay.getByTestId("spot-replay-history-source")).toContainText("Simulated fills");
  // The entry is the declared rule (1-bucket return and quote volume); the exit is the restated 2-bucket return.
  for (let step = 0; step < 3; step += 1) await replay.getByRole("button", { name: "Add entry dependency" }).click();
  await replay.getByLabel("entry dependency offset 2").fill("-1");
  await replay.getByLabel("entry dependency series 3").selectOption("quote_volume");
  await replay.getByRole("button", { name: "Add exit dependency" }).click();
  await replay.getByRole("button", { name: "Add exit dependency" }).click();
  await replay.getByLabel("exit dependency offset 2").fill("-2");
  await replay.getByLabel("I reviewed the entry dependency set").check();
  await replay.getByLabel("I reviewed the exit dependency set").check();
  await replay.getByRole("button", { name: "Save replay on recorded history" }).click();
  const result = replay.getByTestId("spot-replay-result");
  await expect(result).toContainText("Saved replay: complete");
  await expect(result).toContainText("Simulated fills on saved recorded-history dataset");
  await expect(replay.getByTestId("spot-replay-history-lineage")).toContainText(run.declarationId);
  const replayId = (await replay.getByTestId("spot-replay-id").innerText()).trim();
  await shot(page, project, "n3-native-replay");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);
  record(`native-${project}`, { datasetId, nativeRevision, replayId });
});
