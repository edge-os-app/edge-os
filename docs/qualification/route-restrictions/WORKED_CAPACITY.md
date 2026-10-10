# Worked units and capacity examples

Deliverable 5. Independently calculated under the accepted [P15 accounting rules](../../contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md). Prepared 2026-10-10. No new replay, valuation or quantization rule is introduced. Unknown quantities are never zero.

These examples are authored literals. Their success class is `LOCAL_TESTED`. They do not prove provider or chain behavior.

## Units

| Asset | Role | Decimals | Example raw | Decimal value |
|---|---|---|---|---|
| USDC | quote asset | 6 | `1000000000` | 1,000.000000 |
| MON | base asset | 18 | `3000000000000000000000` | 3,000.000000000000000000 |
| MON-native | gas | 18 | `300000000000000000` | 0.300000000000000000 |

Rule: never add raw amounts of different asset IDs. Native MON gas stays separate from WMON and other trading assets.

Wallet W (one agent wallet, network `143`) adopted bounds:

- buy input allowance (USDC): `1000000000` raw.
- sell allowance (MON): `3000000000000000000000` raw.
- attempt budget: `6`.
- gas budget (MON-native): `300000000000000000` raw.

## Example A - two positions share one asset, an unrelated deposit, a competing reservation

P1 entry needs 300 USDC. P2 entry needs 200 USDC. Each entry reserves 2 attempts and 0.004 MON gas (entry 0.002 + retained exit 0.002).

| Quantity | P1 | P2 | Total reserved | Remaining |
|---|---|---|---|---|
| buy input (USDC) | 300 | 200 | 500 | `1000000000 - 500000000 = 500000000` (500 USDC) |
| attempts | 2 | 2 | 4 | `6 - 4 = 2` |
| gas (MON) | 0.004 | 0.004 | 0.008 | `0.3 - 0.008 = 0.292` |

- Unrelated owner deposit of 5,000 USDC: capital flow. It does **not** raise the allowance. Allowance stays 1,000 USDC.
- Competing P3 entry of 600 USDC: `600000000 > 500000000` remaining. **DENIED** (allocation exceeded). The same asset cannot back two commitments.

## Example B - addition and partial exit

- P1 addition of 100 USDC: reserved buy input `500 + 100 = 600` USDC; remaining `400` USDC. The addition reserves its own 2 attempts. Reserved attempts reach 6; remaining attempts 0.
- P2 acquires 1,000 MON actual; the quote estimate was 900 MON. A full intended exit must cover the **attributable inventory** (1,000 MON actual), not the quote estimate and not the whole wallet balance.
- P2 partial exit of 500 MON:
  - sell consumed becomes 500 MON. Remaining sell capacity = `3000 - 500 - outstanding reservations`.
  - removed basis = exited quantity × weighted-average basis immediately before the exit (P15).
  - realized result before fees = reconciled exit proceeds − removed basis, in the same quote asset.
  - the retained inventory must still keep a supported exit path.

## Example C - actual acquisition above the quote estimate

- P1 entry quote output: 900 MON. Actual receipt: 950 MON.
- If a fixed quantity ceiling used a qualified conservative upper bound of 930 MON, the 950 MON actual breaches the model.
- Result: state `BREACHED`. Block new affected admissions for that wallet and network. Retain the residual exposure. Reconcile. Never expand authority to close the gap.

## Example D - external outflow and unknown recovery

- Owner withdrawal of 250 MON: capital flow, not a sale. Reconcile before the affected agent acts again. Do not classify it as a trading result.
- P2 exit returns `SUBMISSION_UNKNOWN`: retain the original signed-reference identity and every reservation. It is not zero spend and not a free retry. No second economic action for that wallet and network until reconciliation.

## Independent arithmetic checks

| Check | Expression | Expected |
|---|---|---|
| Buy input remaining | `1000000000 - 300000000 - 200000000` | `500000000` |
| Buy input after addition | `500000000 - 100000000` | `400000000` |
| Gas reserved (raw) | `4000000000000000 + 4000000000000000` | `8000000000000000` |
| Gas remaining (raw) | `300000000000000000 - 8000000000000000` | `292000000000000000` |
| Minimum output below quote | `950000 <= 1000000` | true |
| Native notional is not the token notional | `msg.value` covers `amountUserSells` only for native input | true |
| Different asset IDs are never summed | `USDC 500` and `MON 500` separate | true |

## Claim boundary

- **Smaller controlled release claim:** one permitted controlled swap under a bounded packet. It proves only that tested operation, authority and recovery boundary.
- **Full-P21 exit-capacity claim (distinct and larger):** covers the full intended exit and attributable inventory across positions. It stays `UNQUALIFIED`. A successful controlled swap does not prove it.
