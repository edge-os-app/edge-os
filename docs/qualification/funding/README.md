# Local funding reconciliation qualification recipe

Task `OC-P18-LOCAL-20261011-01`, issue [#26](https://github.com/edge-os-app/edge-os/issues/26).
This recipe exercises the local preparation in `apps/api/src/edge_os_api/funding/`. It is **not** a
production or provider qualification. No transfer, deposit, provider call, signer, mandate or trading
action is created. The application exposes no funding route. Full issue #26 stays open.

## Evidence classes

| Class | Meaning here |
|---|---|
| `SOURCE_INSPECTED` | An accepted document or contract describes the behavior. |
| `HARNESS_EXECUTED` | The pytest suite ran against real run-labelled PostgreSQL with an authored fake observer. |
| `PROCESS_EXECUTED` | An independent OS process drove the real service against the same database. |
| `PROVIDER_EXECUTED` | **NOT RUN.** No approved provider, RPC or chain call happened. |
| `OWNER_OBSERVED` | **NOT RUN.** No owner took part. |
| `WIRING_EXECUTED` | **NOT RUN.** The module is unwired; no production API/UI route exists. |

A `HARNESS_EXECUTED` or `PROCESS_EXECUTED` result does not imply a provider, chain or owner PASS.

## Run the recipe

From `apps/api`:

```sh
uv sync --frozen
uv run --frozen pytest tests/funding
uv run --frozen pytest
```

From the repository root:

```sh
python3 -B docs/contracts/p02/check_contract.py
python3 -B docs/contracts/p06/check_contract.py
python3 -B docs/contracts/p15/check_contract.py
python3 -B -m unittest discover -s docs/qualification/p16 -p 'test_*.py'
python3 -B -m compileall -q apps/api/src/edge_os_api/funding apps/api/tests/funding
```

The pytest session starts one run-labelled PostgreSQL container, migrates the P02/P06 schema, creates
the owned `funding_local` tables and the accepted P17 `wallet_setup` tables, and removes only its own
container, volume and tables. The `funding_client` fixture adds the test-only router to a fresh app.
The router uses the real `require_principal` and the real verifier with signed test tokens; it is not
production wiring.

## Covered controls

Route-driven (`HARNESS_EXECUTED`, real signed test tokens):

- positive control: a signed owner token declares, prepares and reads a flow;
- negative control: a missing token gets `401`;
- a body-supplied `owner_id` gets `422` and changes no row;
- a cross-owner flow read gets `404`, the same body as an absent record;
- a malformed raw amount or decimals gets `422`;
- a reconcile request credits a confirmed actual once across repeats.

Service and database (`HARNESS_EXECUTED`, real PostgreSQL):

- prepare persists the exact reviewed flow with unknown fields staying `None`, and is idempotent for
  one reference; a changed identity is denied;
- missing and unconfirmed P17 bindings are `404`; an unsupported asset, a withdrawal and a decimals
  mismatch are denied;
- every declared asset must belong to the wallet network, and the gas, trading and compute asset ids
  must be distinct; a testnet asset on a mainnet wallet and a duplicate class are denied;
- a confirmed observation credits the reconciled actual amount once;
- pending, failed and unknown observations stay unavailable;
- a replayed event credits once and records `DUPLICATE`; a conflicting terminal amount fails closed
  with a recorded reason and never overwrites the credit;
- a foreign owner's event on the same wallet string is denied `WRONG_OWNER`, credits nothing and does
  not confirm the requesting owner's flow;
- wrong-wallet, wrong-network (including a wrong-network asset id), unsupported and orphan
  observations are recorded and never credited;
- a declared and an observed fee keep their own asset identity and declared decimals; a fee with no
  asset id, a non-declared asset or wrong decimals stays unknown, never the transfer's asset;
- no cross-wallet or cross-asset pooling; native gas, the trading asset and compute stay separate;
- observation history is preserved; an unavailable observer credits nothing.

Process-driven (`PROCESS_EXECUTED`, independent OS processes against the same database):

- a crash during observation leaves no credit; a restart reconciles the same reference and credits
  once, and a second restart credits nothing;
- a crash after the credit commit leaves one credit; a restart credits nothing further;
- two concurrent reconciles of the same event credit exactly once.

WAL-Q22 invariance (`HARNESS_EXECUTED`):

- a confirmed deposit leaves the full-row digest of the admission allowance and reservation rows and
  the accepted P17 binding row unchanged, while the funding credit is the only change.

## Current results

Recorded in the worker evidence directory `.scratch/wallet-wave/p18/evidence/`. Candidate identity,
command output, timings and the contributed-table digest are captured there. Provider, owner, real
transport and shared-wiring checks are `NOT RUN`; browser and live checks are not claimed because the
module is unwired.
