# Local wallet-setup qualification recipe

Task `OC-P17-LOCAL-20261010-01`, issue [#22](https://github.com/edge-os-app/edge-os/issues/22).
This recipe exercises the local preparation in `apps/api/src/edge_os_api/wallet_setup/`. It is
**not** a production or provider qualification. No wallet, signer, funding, mandate or trading
action is created. The application exposes no wallet setup route. Full P17 stays open.

## Evidence classes

| Class | Meaning here |
|---|---|
| `SOURCE_INSPECTED` | An accepted document or contract describes the behavior. |
| `HARNESS_EXECUTED` | The pytest suite ran against real run-labelled PostgreSQL with an authored fake provider. |
| `PROCESS_EXECUTED` | An independent OS process drove the real service against the same database. |
| `PROVIDER_EXECUTED` | **NOT RUN.** No approved Privy or provider call happened. |
| `OWNER_OBSERVED` | **NOT RUN.** No owner took part. |

A `HARNESS_EXECUTED` or `PROCESS_EXECUTED` result does not imply a provider or owner PASS.

## Run the recipe

From `apps/api`:

```sh
uv sync --frozen
uv run --frozen pytest tests/wallet_setup tests/test_auth.py tests/test_ownership.py tests/test_publication.py
uv run --frozen pytest
```

From the repository root:

```sh
python3 -B docs/contracts/p02/check_contract.py
python3 -B docs/contracts/p06/check_contract.py
python3 -B docs/contracts/p15/check_contract.py
python3 -B -m unittest discover -s docs/qualification/p16 -p 'test_*.py'
python3 -B -m compileall -q apps/api/src/edge_os_api/wallet_setup apps/api/tests/wallet_setup
```

The pytest session starts one run-labelled PostgreSQL container, migrates the P02/P06 schema,
creates only the `wallet_setup_local` tables, and removes only its own container and volume. The
`wallet_client` fixture adds the test-only router to a fresh app. The router uses the real
`require_principal` and the real verifier with signed test tokens; it is not production wiring.

## Covered controls

Route-driven (`HARNESS_EXECUTED`, real signed test tokens):

- positive control: a signed owner token prepares and confirms a setup;
- negative control: a missing token gets `401 auth_required`;
- cross-owner read and dispatch get `404`, the same body as an absent agent;
- a body-supplied `owner_id` gets `422` and changes no row;
- a foreign or random strategy revision gets `404` and creates no row;
- a changed network or revision for one agent gets `409 changed_setup_identity` and changes nothing;
- one wallet binding per agent across replays and a new request key;
- a second agent gets a distinct wallet;
- a proved pre-dispatch cancel causes zero creation calls;
- a lost response stays `UNKNOWN` and never retries creation;
- wrong-owner provider evidence stays `UNKNOWN`;
- a conflicting wallet never overwrites a confirmed binding;
- a mutation request that asserts an owner, wallet, setup, network or revision is rejected `422`
  before any call and changes no protected state;
- a malformed creation or lookup result, including a malformed field inside a valid-looking
  `WalletEvidence`, becomes durable `UNKNOWN` with a reason, never a `500`;
- research saves and reads a revision with no wallet.

Process-driven (`PROCESS_EXECUTED`, independent OS processes against the same database):

- a fresh process reloads the same binding unchanged;
- a crash during dispatch leaves one durable dispatch intent and no second creation;
- a crash after the result but before the binding reconciles one exact retained late result;
- a resumed unchanged wallet ID with a changed address stays `UNKNOWN` and does not bind;
- a concurrent valid prepare returns the same setup and never fails on the unique constraint;
- two independent processes create exactly one wallet.

## Current results

Recorded in the worker evidence directory `.scratch/p17-l3/evidence/`. Baseline candidate identity,
command output, timings and the contributed-table digest are captured there. Provider and owner
checks are `NOT RUN`; browser and live checks are not claimed because the module is unwired.
