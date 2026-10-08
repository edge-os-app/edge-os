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
  it("marks synthetic assumptions as synthetic", () => {
    expect(summarizeValue("cost_assumptions", { fee_rate: "0.003", slippage_rate: "0.005", source_ref: "x" })).toMatch(/synthetic assumption/);
    expect(summarizeValue("market", {})).toMatch(/not a real pool/);
  });
});

describe("percent formatting is exact", () => {
  const cmp = (value: string) => ({ op: "gt", args: [{ op: "price_return", lookback_buckets: 1 }, { op: "constant", value, unit: "DIMENSIONLESS" }] });
  it.each([["0.07", "7%"], ["0.29", "29%"], ["0.00004", "0.004%"], ["0.00125", "0.125%"], ["0.035", "3.5%"], ["0.5", "50%"], ["1", "100%"], ["0.01", "1%"]])(
    "renders %s as %s", (value, expected) => {
      expect(describeExpression(cmp(value))).toBe(`price rose more than ${expected} over the last 5 minutes`);
    });
});
