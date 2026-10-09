import { describe, expect, it } from "vitest";
import { actionsForPosition, filterPositions, formatAmount, type AccountViewRecord } from "../lib/account-views";

const records: AccountViewRecord[] = [
  { record_id: "pa1", owner_id: "owner-a", content: {
    owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "POSITION", agent_id: "agent-a", wallet_id: "wallet-a",
    network_id: "monad:143", asset_id: "monad:143/asset:MOE", position_id: "position-a-1",
    strategy_revision: "strategy-a-v3", mandate_id: "mandate-a-v1", position_state: "OPEN", status: "OPEN",
    updated_at: "2026-10-09T11:00:00Z", quantity: { asset_id: "monad:143/asset:MOE", raw: "15", decimals: 0 },
  } },
  { record_id: "pa2", owner_id: "owner-a", content: {
    owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "POSITION", agent_id: "agent-a", wallet_id: "wallet-a",
    network_id: "monad:143", asset_id: "monad:143/asset:MOE", position_id: "position-a-2",
    strategy_revision: "strategy-a-v2", mandate_id: "mandate-a-v0", position_state: "OPEN", status: "OPEN",
    updated_at: "2026-10-09T11:00:00Z", quantity: { asset_id: "monad:143/asset:MOE", raw: "4", decimals: 0 },
  } },
  { record_id: "action-a", owner_id: "owner-a", content: {
    owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "ACTION", agent_id: "agent-a", wallet_id: "wallet-a",
    network_id: "monad:143", asset_id: "monad:143/asset:MOE", position_id: "position-a-1",
    strategy_revision: "strategy-a-v3", mandate_id: "mandate-a-v1", action_id: "sale-a", status: "SUBMITTED",
    updated_at: "2026-10-09T11:01:00Z", quantity: { asset_id: "monad:143/asset:MOE", raw: "3", decimals: 0 },
  } },
  { record_id: "action-b", owner_id: "owner-a", content: {
    owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "ACTION", agent_id: "agent-b", wallet_id: "wallet-b",
    network_id: "monad:143", asset_id: "monad:143/asset:MOE", position_id: "position-b-1",
    strategy_revision: "strategy-b-v1", mandate_id: "mandate-b-v1", action_id: "sale-b", status: "CONFIRMED",
    updated_at: "2026-10-09T11:02:00Z", quantity: { asset_id: "monad:143/asset:MOE", raw: "2", decimals: 0 },
  } },
];

describe("account view record identity", () => {
  it("formats exact raw amounts without floating-point conversion", () => {
    expect(formatAmount({ asset_id: "monad:143/asset:MON", raw: "50000000000000000", decimals: 18 })).toBe("0.05");
    expect(formatAmount({ asset_id: "monad:143/asset:MOE", raw: "1000", decimals: 0 })).toBe("1000");
  });

  it("filters exact agent, wallet, and asset identities", () => {
    const positions = records.filter((record) => record.content.record_kind === "POSITION");
    expect(filterPositions(positions, { agent_id: "agent-a", wallet_id: "wallet-a", asset_id: "monad:143/asset:MOE" }))
      .toHaveLength(2);
    expect(filterPositions(positions, { wallet_id: "wallet-b" })).toEqual([]);
  });

  it("shows only actions that match the complete position identity", () => {
    const position = records[0];
    expect(actionsForPosition(records, position)).toEqual([records[2]]);
  });
});
