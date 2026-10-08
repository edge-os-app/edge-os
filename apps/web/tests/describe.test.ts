import { describe, expect, it } from "vitest";
import { describeExpression, summarizeValue } from "../lib/describe";

const gt = (buckets: number, value: string) => ({ op: "gt", args: [{ op: "price_return", lookback_buckets: buckets }, { op: "constant", value, unit: "DIMENSIONLESS" }] });

describe("plain-words rules", () => {
  it("reads a threshold with the exact percentage and minutes", () => {
    expect(describeExpression(gt(3, "0.01"))).toBe("price rose more than 1% over the last 15 minutes");
    expect(describeExpression(gt(6, "0.035"))).toBe("price rose more than 3.5% over the last 30 minutes");
  });
  it("keeps the direction of the rule: a return below zero is a fall", () => {
    const cmp = (op: string, value: string) => ({ op, args: [{ op: "price_return", lookback_buckets: 1 }, { op: "constant", value, unit: "DIMENSIONLESS" }] });
    expect(describeExpression(cmp("lt", "0"))).toBe("price fell over the last 5 minutes");
    expect(describeExpression(cmp("gt", "0"))).toBe("price rose over the last 5 minutes");
    expect(describeExpression(cmp("lt", "-0.02"))).toBe("price fell more than 2% over the last 5 minutes");
    expect(describeExpression(cmp("lt", "0.02"))).toBe("the 5-minute price return is below 2%");
    expect(describeExpression(cmp("gt", "-0.02"))).toBe("the 5-minute price return is above -2%");
  });
  it("states that action scope grants no permission", () => {
    expect(summarizeValue("action_scope", ["SPOT_BUY"])).toMatch(/grants no permission/);
  });
  it("explains the quote-volume baseline and its scheduled timing", () => {
    expect(describeExpression({ op: "relative_volume", lookback_buckets: 3 }))
      .toBe("current quote volume divided by the mean of the previous 15 minutes");
  });
  it("keeps nested Boolean groups visible in the review text", () => {
    const a = { op: "gt", args: [{ op: "relative_volume", lookback_buckets: 2 }, { op: "constant", value: "2", unit: "DIMENSIONLESS" }] };
    const b = { op: "gt", args: [{ op: "price" }, { op: "constant", value: "20", unit: "PRICE" }] };
    const c = { op: "gt", args: [{ op: "price" }, { op: "constant", value: "30", unit: "PRICE" }] };

    expect(describeExpression({ op: "and", args: [{ op: "or", args: [a, b] }, c] }))
      .toBe("(current quote volume divided by the mean of the previous 10 minutes is above 2 or price is above 20) and price is above 30");
    expect(describeExpression({ op: "or", args: [a, { op: "and", args: [b, c] }] }))
      .toBe("current quote volume divided by the mean of the previous 10 minutes is above 2 or (price is above 20 and price is above 30)");
    expect(describeExpression({ op: "and", args: [{ op: "not", value: { op: "or", args: [a, b] } }, c] }))
      .toBe("not (current quote volume divided by the mean of the previous 10 minutes is above 2 or price is above 20) and price is above 30");
  });
  it("marks synthetic assumptions as synthetic", () => {
    expect(summarizeValue("cost_assumptions", { fee_rate: "0.003", slippage_rate: "0.005", source_ref: "x" })).toMatch(/synthetic assumption/);
    expect(summarizeValue("market", { network: "MONAD", research_binding: { evidence_class: "SYNTHETIC_FIXTURE" } })).toMatch(/not a real pool/);
  });
  it("names the market from its value, never from a fixed label", () => {
    const text = summarizeValue("market", { network: "MONAD", base_asset: "0xabababababababababababababababababababab", quote_asset: "0xcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd" });
    expect(text).not.toMatch(/not a real pool/);
    expect(text).toMatch(/0xabab/);
    expect(text).toMatch(/0xcdcd/);
  });
});

describe("percent formatting is exact", () => {
  const cmp = (value: string, op = "gt") => ({ op, args: [{ op: "price_return", lookback_buckets: 1 }, { op: "constant", value, unit: "DIMENSIONLESS" }] });
  it.each([["0.07", "7%"], ["0.29", "29%"], ["0.00004", "0.004%"], ["0.00125", "0.125%"], ["0.035", "3.5%"], ["0.5", "50%"], ["1", "100%"], ["0.01", "1%"]])(
    "renders %s as %s", (value, expected) => {
      expect(describeExpression(cmp(value))).toBe(`price rose more than ${expected} over the last 5 minutes`);
    });
  it("preserves nonzero decimal thresholds that underflow JavaScript Number", () => {
    const positiveTiny = `0.${"0".repeat(399)}1`;
    const negativeTiny = `-${positiveTiny}`;
    const percentPositiveTiny = `0.${"0".repeat(397)}1%`;

    expect(describeExpression(cmp(positiveTiny)))
      .toBe(`price rose more than ${percentPositiveTiny} over the last 5 minutes`);
    expect(describeExpression(cmp(positiveTiny, "gte")))
      .toBe(`price rose at least ${percentPositiveTiny} over the last 5 minutes`);
    expect(describeExpression(cmp(positiveTiny, "lt")))
      .toBe(`the 5-minute price return is below ${percentPositiveTiny}`);
    expect(describeExpression(cmp(positiveTiny, "lte")))
      .toBe(`the 5-minute price return is at or below ${percentPositiveTiny}`);
    expect(describeExpression(cmp(negativeTiny)))
      .toBe(`the 5-minute price return is above -0.${"0".repeat(397)}1%`);
    expect(describeExpression(cmp(negativeTiny, "gte")))
      .toBe(`the 5-minute price return is at or above -0.${"0".repeat(397)}1%`);
    expect(describeExpression(cmp(negativeTiny, "lt")))
      .toBe(`price fell more than ${percentPositiveTiny} over the last 5 minutes`);
    expect(describeExpression(cmp(negativeTiny, "lte")))
      .toBe(`price fell at least ${percentPositiveTiny} over the last 5 minutes`);
    expect(describeExpression(cmp("0"))).toBe("price rose over the last 5 minutes");
  });
});
