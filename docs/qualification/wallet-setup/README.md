# Local wallet-setup qualification recipe

Task `OC-P17-WIRING-20261011-01`, issue [#22](https://github.com/edge-os-app/edge-os/issues/22).
This recipe exercises the wired wallet setup in `apps/api/src/edge_os_api/wallet_setup/` over the
application's own authenticated routes. It is **not** a production or provider qualification. No
wallet, signer, funding, mandate or trading action is created. The only provider is an authored
local fixture, refused in production; the real provider stays fail-closed. Full P17 stays open.

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

The pytest session starts one run-labelled PostgreSQL container, migrates the P02/P06 schema plus
the additive `0007_wallet_setup` tables, and removes only its own container and volume. The
`wallet_client` fixture builds the real application and points `app.state.wallet_provider` at a
controlled authored fake; the routes are the application's own mounted router, which uses the real
`require_principal` and the real verifier with signed test tokens. The unmounted fake is the only
test seam. The full `scripts/p03/verify_run.py` recipe additionally drives the mounted routes
through the browser with the local fixture provider enabled.

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
- a proved pre-dispatch cancel records no dispatch intent and makes no provider call;
- a lost response stays `UNKNOWN` and never retries creation;
- wrong-owner provider evidence stays `UNKNOWN`;
- a conflicting wallet never overwrites a confirmed binding;
- a mutation request that asserts an owner, wallet, setup, network or revision is rejected `422`
  before any call and changes no protected state;
- a malformed creation or lookup result, including a malformed, unstorable or unencodable field
  inside a valid-looking `WalletEvidence`, becomes durable `UNKNOWN` with a reason, never a `500`,
  while valid non-ASCII text is accepted;
- research saves and reads a revision with no wallet.

Process-driven (`PROCESS_EXECUTED`, independent OS processes against the same database):

- a fresh process reloads the same binding unchanged;
- a crash during dispatch leaves one durable dispatch intent and no second creation;
- a crash after the result but before the binding reconciles one exact retained late result;
- a resumed unchanged wallet ID with a changed address stays `UNKNOWN` and does not bind;
- a concurrent valid prepare returns the same setup and never fails on the unique constraint;
- two independent processes create exactly one wallet.

## Current results

Recorded in the worker evidence directory `.scratch/wallet-wave/p17/evidence/`. Baseline candidate
identity, command output, timings and the verify-edge-os recipe run are captured there. Provider
and owner checks are `NOT RUN`; the browser checks run only against the authored local fixture and
prove the wiring, never a real provider. Full P17 (real provider qualification) stays open.
