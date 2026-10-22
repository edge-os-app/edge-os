# Operator-run WMON -> MOE trade (one command, dry run first)

Status: local implementation. The controller runs the dry run against the live chain. The controller
runs the live command only after the builder approves it. This document grants no trade authority.

## What it does

`python -m scripts.operator_trade.run` runs one fixed sequence on Monad chain `143` from the agent
wallet:

1. Preflight reads only: chain id, block, MON balance, WMON balance and allowance, pool tokens and
   reserves, code SHA256 of the entrypoint, WMON and pool, nonce, base fee and priority fee.
2. Plan: expected MOE output with the pinned direct-route formula, the local minimum, and the
   worst-case cost. The cost is the input value plus gas for all four transactions.
3. Four type-2 transactions, in order, each signed through `PrivySignerClient.eth_signTransaction`
   only and sent once with `eth_sendRawTransaction`:
   - wrap: WMON `deposit()` with value X;
   - approve: WMON `approve(entrypoint, X)` exactly;
   - swap: the merged `build_calldata_hex` call for this pool and minimum, value 0;
   - revoke: WMON `approve(entrypoint, 0)`.
4. Post-checks: allowance is 0, MOE increased by at least the minimum, WMON decreased by exactly X,
   and the entrypoint code SHA256 is unchanged.

The swap calldata comes from the merged application module
`apps/api/src/edge_os_api/execution/direct_route_quote_client.py`. The script does not copy or
re-implement that builder.

## Honest limits

- This is an **operator-run** command. It is not the app's ACTUAL transaction journey.
- The trade file is pinned to the one approved wallet, wallet id, token pair, pool, entrypoint,
  direction `0` and program fee `16000`. The script refuses any other value.
- The in-app path still lacks a `/rpc` relay, wrap/approve/revoke steps, the 12-control evidence,
  position inventory and a mounted runtime.
- The video must label the trade "operator-run, app-built calldata".
- The installed `PrivySignerClient` refuses a transaction quantity above `2**53-1`. A wrap of about
  60 MON is above that limit. The script stops before signing such a wrap, with no broadcast. Lane 3
  (`UNFUNDED-POLICY-PROOF-L3`) changes the signer; this script uses only the signer's public
  interface and does not edit it. The test that needs that change skips only after it checks the
  signer's actual behavior; the skip reason names lane 3.
- The dry run uses WMON storage slots `3` (balance) and `4` (allowance) for state overrides. The
  builder's 2026-10-22 live check confirmed this layout. These slots are WMON-specific; they are
  simulation inputs only.
- The script reads chain state at one block. It cannot prove mempool ordering or later pool state.
- The script uses sequential nonces from one preflight read. It waits for status `1` after each step.

## Trade file

The trade file is a frozen JSON document. The builder approves exactly one file. `--live` requires
its SHA256. Unknown fields are refused. A second file with a different amount needs a new approval.

| Field | Meaning |
| --- | --- |
| `version` | Must be `1`. |
| `chain_id` | Must be `143`. |
| `wallet_address` | The one approved agent wallet. Must match the policy wallet. |
| `wallet_id` | The one approved Privy wallet id (a public identifier). |
| `wmon`, `moe` | Token addresses. Must match the pinned WMON and MOE. |
| `pool` | The one pinned Kuru pool. |
| `entrypoint` | The pinned Kuru Flow entrypoint. |
| `token0`, `token1` | Pinned pool token order. Must equal WMON then MOE. |
| `direction` | Must be `0` (token0 to token1). |
| `program_fee_ppm` | Must be `16000`. |
| `input_raw` | Input amount in WMON raw units, as a decimal string. Maximum 70 MON. |
| `slippage_bps` | Minimum output slippage in basis points. `0` to `10000`. |
| `usd_ceiling` | Worst-case USD ceiling. Must be at most `2.00`. |
| `mon_usd_price` | MON/USD price used for the cost check, as a decimal string. |
| `gas_limits` | Object with `wrap`, `approve`, `swap`, `revoke` gas limits. |
| `code_sha256` | Object with `entrypoint`, `wmon`, `pool` code SHA256 values. |
| `receipt_timeout_seconds` | Bounded wait for each receipt. |
| `receipt_poll_seconds` | Poll interval for each receipt. |

The example `trade.example.json` is not approved and not a trade authorization. Its `wmon` and
`pool` code hashes are zero placeholders. Run the dry run once; on a mismatch the refusal reports
the observed hash for each role. Freeze the observed hashes in a new file before approval.

Worst-case cost, in MON:

```text
(input_raw + (wrap + approve + swap + revoke) * max_fee_per_gas) / 10**18
```

`max_fee_per_gas = 2 * base_fee + priority_fee`. The script refuses when the USD value is above the
trade file ceiling. The ceiling itself is refused above `2.00`.

## Commands

Run from the repository root. The application environment is `apps/api/.venv`.

Dry run (the default):

```sh
EDGE_OS_OPERATOR_RPC_URL=... \
apps/api/.venv/bin/python -m scripts.operator_trade.run --trade-file path/to/trade.json
```

Live run:

```sh
EDGE_OS_OPERATOR_RPC_URL=... \
EDGE_OS_PRIVY_APP_ID=... \
EDGE_OS_PRIVY_APP_SECRET=... \
EDGE_OS_PRIVY_AGENT_KEY_FILE=/path/to/agent-key.pem \
apps/api/.venv/bin/python -m scripts.operator_trade.run \
  --live --trade-file path/to/trade.json \
  --confirm <sha256 of that file> --store path/to/new-empty-store
```

Environment variables (live only, except the RPC URL which both modes need):

- `EDGE_OS_OPERATOR_RPC_URL`: the JSON-RPC endpoint. It can contain a key, so the script never
  prints or journals it.
- `EDGE_OS_PRIVY_APP_ID`
- `EDGE_OS_PRIVY_APP_SECRET`
- `EDGE_OS_PRIVY_AGENT_KEY_FILE`: the P-256 agent signer key file.

The script does not read `edge-os/.env` by itself. It reads only the process environment.

`--dry-run` is the default. It builds the four unsigned transactions, simulates them in order with
`eth_call` and state overrides, prints the plan and cost, and returns. It loads no Privy
credential, constructs no signer, writes no store and cannot call `eth_sendRawTransaction`.

`--live` requires all of these:

- the exact trade file SHA256 in `--confirm`;
- a new empty `--store` directory;
- the four environment values above.

`--live` with `--dry-run`, or `--store` with a dry run, is refused.

## Evidence

The live store holds two files:

- `journal.jsonl`: one JSON line per event, written and fsynced before the next external effect.
  Events: `prepared`, `before_send`, `sent`, `confirmed`, `sign_refused`, `sign_unknown`,
  `unknown`, `receipt_timeout`. Each step record holds the request hash and nonce; `before_send`
  also holds the signed transaction hash.
- `result.json`: the plan, every step with nonce, request hash, transaction hash, receipt block and
  gas used, the post-checks, and the outcome.

A second run with the same store is refused. The script never sends a step again after an unknown
outcome. If the swap fails after the approve succeeded, the script attempts the revoke once and
records the result.

## Refusal codes

The command prints one JSON line with `status: REFUSED` and a stable code. Important codes:

- `TRADE_FILE_INVALID`, `TRADE_FILE_UNREADABLE`
- `CONFIRM_REQUIRED`, `CONFIRM_MISMATCH`
- `STORE_REQUIRED`, `STORE_NOT_EMPTY`
- `ENV_MISSING`, `KEY_FILE_UNREADABLE`, `KEY_FILE_INVALID`
- `RPC_ENDPOINT_INVALID`, `RPC_REFUSED`, `RPC_REPLY_LOST`
- `CHAIN_ID_MISMATCH`, `TOKEN_ORDER_MISMATCH`, `CODE_HASH_MISMATCH`, `ALLOWANCE_NOT_ZERO`
- `INSUFFICIENT_NATIVE_BALANCE`, `USD_CEILING_EXCEEDED`, `FEE_ABOVE_SIGNER_LIMIT`
- `SIMULATION_FAILED`, `SIMULATION_BELOW_MINIMUM`
- `SIGNER_REFUSED`, `SIGNER_REPLY_LOST`, `SIGNER_REPLY_INVALID`
- `BROADCAST_UNKNOWN`, `RECEIPT_TIMEOUT`, `RECEIPT_STATUS_FAILED`

## Who enforces which control

Privy enforces (from `ROOT/.scratch/trade-prep-20261021/PRIVY_SETUP1.json`):

- R1: `deposit()` on WMON, value at most 70 MON.
- R2: `approve()` on WMON, spender the entrypoint, amount at most 70 WMON, value 0.
- R3: `executeSwap` or `executeSwapWithReceiver` on the entrypoint, value 0.

The script and the host enforce:

- one chain (`143`) and one wallet;
- pinned token order, pool, entrypoint and code hashes;
- a zero start allowance;
- the exact input value and the exact approve amount;
- the merged calldata builder and the local minimum output;
- the bounded worst-case cost, including gas for all four transactions, against USD 2.00;
- journal-before-send, no resend, and the bounded receipt wait;
- revoke to 0, including after a failed swap;
- the four post-checks.

The policy does not enforce controls 5-8 of the 12-control model (exact input, recipient, minimum
received, fees); the entrypoint and this script enforce the parts they can. Control 4 (input and
output token inside the swap call) stays recorded as UNKNOWN for Privy.

## Tests

Tests live in `apps/api/tests/operator_trade/`. This location keeps the repository's pytest
configuration (`apps/api/pyproject.toml`, `pythonpath = src`) and the required comparison suites in
one project. A package `conftest.py` adds the repository root for `scripts.operator_trade` and
blocks sockets in every test.

Run them with:

```sh
cd apps/api && .venv/bin/python -m pytest tests/operator_trade
```

One named test skips when the installed signer refuses quantities above `2**53-1`. The skip
condition reads the signer's behavior. It is not a silent pass.
