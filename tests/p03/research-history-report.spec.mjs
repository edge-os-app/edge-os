/**
 * #58 Task 6, phase 2 of 3, after one worker pass: saved reports, source loss, the killed-worker job, retry, then a
 * strategy that adopts the recorded market as a NEW draft, is published, and replays with simulated fills on the
 * saved dataset. The first (fixture-market) revision still cannot replay on that market. SYNTHETIC recordings only.
 */
import { test, expect } from "@playwright/test";
import { tokens } from "./fixture-auth.mjs";
import { apiGet, apiPost, historySection, jobsFor, noSeriousAxe, noSidewaysScroll, open, openDeclaration, record, sample, saved,
  shot } from "./research-flow.mjs";

const THESIS = "Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. Spot only.";

test("reports, stopped jobs, retry, market adoption, publication and labelled replay", async ({ page }, info) => {
  const project = info.project.name;
  const run = saved(`research-${project}`);
  await open(page, tokens.a);
  const section = await historySection(page, run.url);

  await openDeclaration(section, run.hypothesis);
  const cards = section.getByTestId("history-job");
  await expect(cards.nth(0)).toHaveAttribute("data-state", "REPORTED");
  await expect(cards.nth(1)).toHaveAttribute("data-state", "CANCELLED");
  await expect(cards.nth(2)).toHaveAttribute("data-state", "REPORTED");
  await expect(cards.nth(3)).toHaveAttribute("data-state", "UNAVAILABLE");
  await expect(cards.nth(3)).toContainText("not collected again");
  const report = cards.nth(0).getByTestId("history-report");
  await expect(report).toContainText("RECORDED_RESPONSE; SYNTHETIC_FIXTURE; verdict QUALIFIED");
  await expect(report).toContainText("significance NOT_CLAIMED; capital authority NONE");
  await expect(report).toContainText("Not read: VALIDATION partition, HOLDOUT partition");
  const reportId = (await report.getByTestId("history-report-id").innerText()).trim();
  const datasetId = (await report.getByTestId("history-report-dataset").innerText()).trim();
  await shot(page, project, "05-report");

  // The killed worker's original attempt is not collected again; a retry is a new job with its own reservation.
  await cards.nth(3).getByRole("button", { name: "Retry as a new job" }).click();
  await expect(cards).toHaveCount(5);
  await expect(cards.nth(4)).toHaveAttribute("data-state", "RESERVED");
  const mainJobs = await jobsFor(page, tokens.a, run.intakeId, run.main);
  expect(mainJobs[3].budget.unknown_liability.provider_requests).toBe(2);
  expect(mainJobs[3].events.map((event) => event.kind)).toContain("ATTEMPT_RECONCILED");

  await openDeclaration(section, `Provider loss case (${project})`);
  const loss = section.getByTestId("history-job").first();
  await expect(loss).toHaveAttribute("data-state", "REPORTED");
  await expect(loss.getByTestId("history-report")).toContainText("Saved report: SOURCE_LOSS");
  await expect(loss).toContainText("PARTIAL, LIMITED, UNAVAILABLE_LIMITED_DATA");
  await shot(page, project, "06-source-loss");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);

  // A strategy request: save the fixture-market revision, then adopt the recorded market as a NEW draft.
  await page.goto("/");
  await sample(page, "Specific thesis").click();
  await page.getByRole("button", { name: "Prepare request" }).click();
  await page.getByRole("button", { name: "Adopt these settings" }).first().click();
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const strategyUrl = page.url();
  const strategyIntake = decodeURIComponent(strategyUrl.split("/").pop() ?? "");
  const fixtureRevision = (await page.getByTestId("revision-id").innerText()).trim();

  const adoption = page.getByTestId("market-adoption");
  await adoption.getByLabel("Saved dataset").selectOption(datasetId);
  const reviewBox = adoption.getByTestId("market-adoption-review");
  await expect(reviewBox).toContainText("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
  await expect(reviewBox).toContainText("QUOTE:0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
  await expect(reviewBox).toContainText("route qualification UNQUALIFIED");
  await expect(adoption.getByLabel("Trade size in the new quote unit")).toHaveValue("");
  await expect(adoption.getByRole("button", { name: "Adopt this market for a new draft" })).toBeDisabled();
  await adoption.getByLabel("Trade size in the new quote unit").fill("50");
  await adoption.getByLabel("Largest position value in the new quote unit").fill("50");
  await expect(adoption.getByRole("checkbox")).toBeDisabled(); // a declared entry rule and an own exit rule are required
  const declaredRule = (await apiGet(page, tokens.a, "/v1/research/history-datasets")).body.datasets
    .find((item) => item.dataset_id === datasetId).declared_rules[0];
  await adoption.getByLabel("Entry rule (one you declared for this dataset)").selectOption(declaredRule.evaluation_id);
  await adoption.getByLabel("Exit lookback (buckets)").fill("2");
  await adoption.getByLabel("Exit threshold (fraction, for example -0.001)").fill("-0.001");
  await adoption.getByRole("checkbox").check();
  await shot(page, project, "07-adopt-market");
  await adoption.getByRole("button", { name: "Adopt this market for a new draft" }).click();
  await expect(adoption.getByRole("status")).toContainText("uses the recorded market");
  await expect(page.getByTestId("outcome")).toHaveAttribute("data-outcome", "COMPILED");
  await page.getByRole("button", { name: "Save this revision" }).click();
  await expect(page.getByTestId("revision")).toContainText("Read back from the database");
  const historyRevision = (await page.getByTestId("revision-id").innerText()).trim();
  expect(historyRevision).not.toBe(fixtureRevision);

  // Simulated fills on the saved dataset, through the unchanged replay runtime.
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
  await expect(result).toContainText("BUY_FILLED");
  await expect(result).toContainText("Simulated fills on saved recorded-history dataset");
  await expect(replay.getByTestId("spot-replay-history-lineage")).toContainText(run.main);
  await expect(replay.getByTestId("spot-replay-history-lineage")).toContainText(`The declared rule ${declaredRule.evaluation_id}`);
  const replayId = (await replay.getByTestId("spot-replay-id").innerText()).trim();
  await shot(page, project, "08-history-replay");
  if (project === "mobile-390") await noSidewaysScroll(page);
  await noSeriousAxe(page);

  // The original fixture-market revision stays unchanged and still cannot use the recorded market.
  const strategyId = (await apiGet(page, tokens.a, `/v1/research/requests/${strategyIntake}`)).body.head.strategy_id;
  const mismatch = await apiPost(page, tokens.a, "/v1/spot-replays", {
    idempotency_key: `rg05-mismatch-${crypto.randomUUID()}`, strategy_id: strategyId, strategy_revision_id: fixtureRevision,
    history_dataset_id: datasetId, run_configuration_id: `rg05-mismatch-${crypto.randomUUID()}`,
    window_start: "2026-09-25T10:20:00Z", window_end: "2026-09-25T11:00:00Z", initial_cash_quote: "1000",
    initial_base_amount: "0", initial_basis_quote: "0", essential_fields: {
      entry: { state: "BOUND", essential_dependencies: [{ series: "price", offset_buckets: 0 }, { series: "price", offset_buckets: -3 }] },
      exit: { state: "BOUND", essential_dependencies: [{ series: "price", offset_buckets: 0 }, { series: "price", offset_buckets: -1 }] } } });
  expect(mismatch.status).toBe(201);
  expect(mismatch.body.content.result.reason.code).toBe("MARKET_BINDING_MISMATCH");
  // Validation and holdout buckets of the declaration are never replayed.
  const protectedReplay = await apiPost(page, tokens.a, "/v1/spot-replays", {
    idempotency_key: `rg05-protected-${crypto.randomUUID()}`, strategy_id: strategyId, strategy_revision_id: historyRevision,
    history_dataset_id: datasetId, run_configuration_id: `rg05-protected-${crypto.randomUUID()}`,
    window_start: "2026-09-25T10:20:00Z", window_end: "2026-09-25T11:05:00Z", initial_cash_quote: "1000",
    initial_base_amount: "0", initial_basis_quote: "0", essential_fields: {
      entry: { state: "BOUND", essential_dependencies: [{ series: "price", offset_buckets: 0 }] },
      exit: { state: "BOUND", essential_dependencies: [{ series: "price", offset_buckets: 0 }] } } });
  expect(protectedReplay.status).toBe(409);
  expect(protectedReplay.body.code).toBe("protected_partition_not_authorized");

  record(`research-${project}`, { reportId, datasetId, strategyUrl, strategyIntake, strategyId, fixtureRevision,
    historyRevision, replayId, mismatchReplayId: mismatch.body.replay_id });
});
