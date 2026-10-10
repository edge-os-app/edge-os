# P21 selected-route restrictions and failure checks

Task OC-P21-PREP-20261010-01. GitHub issue #20. Worker pane `%9`, branch `ticket/p21-route-restrictions`, base `9c494f1e6eb154fb76dba2e955a2628fd7e7cb63`. Prepared 2026-10-10.

Stage: **documentation and offline preparation only.** This package defines the mandatory controlled-action restrictions for the selected Kuru Flow fixed-input route, an executable offline checker with adversarial cases, independently worked capacity examples and one bounded future live-test packet.

It does not run a provider request, create or fund a wallet, claim a faucet, sign, broadcast, swap or change a policy. Full P21 issue #20 stays OPEN.

## Proposed verdicts

- **DOCUMENTATION / PREPARATION: PASS within the stated scope.** The route's mandatory controls are mapped to their enforcement layer and evidence class. The offline checker rejects missing, unknown or unsupported mandatory controls and every one-field adversarial mutation.
- **LIVE qualification: NOT_RUN.** No route/network/ABI transport, policy, wallet, funding, signature, broadcast or receipt evidence exists. Testnet Flow support stays `UNKNOWN`. The opaque route `program` and the exact gas/action capacity stay `UNQUALIFIED`.

A passing offline case is always `AUTHORED_FAKE_ONLY`. It is never `REAL_READY` and never a live approval.

## Documents

- [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md) - exact URLs, dates, pins, the bounded read-only RPC log and content hashes.
- [NETWORK_DECISION.md](NETWORK_DECISION.md) - network eligibility and the route-based network decision, with unknowns.
- [CONTROL_RESTRICTIONS.md](CONTROL_RESTRICTIONS.md) - the mandatory-control matrix and each control's enforcement layer and evidence class.
- [WORKED_CAPACITY.md](WORKED_CAPACITY.md) - independent units and capacity arithmetic under the accepted P15 rules.
- [LIVE_TEST_PACKET.md](LIVE_TEST_PACKET.md) - the one bounded future release proposal and its acceptance sequence.
- [restriction_checker.py](restriction_checker.py) and [fixtures.json](fixtures.json) - the offline checker and its authored fixtures.
- [test_restriction_checker.py](test_restriction_checker.py) - the offline unit tests.

The implementation-facing summary is `docs/implementation/ROUTE_RESTRICTIONS_PROFILE.md`.

## Run the offline checks

From the repository root:

```sh
python3 -B -m unittest discover -s docs/qualification/route-restrictions -p 'test_*.py' -v
python3 -B docs/qualification/route-restrictions/restriction_checker.py
```

The checker uses Python's standard library only. It loads one authored fixture file. It has no network, wallet, signing, provider or broadcast code path. The test suite proves that property by inspecting the checker's imports and by running the default command.

## Evidence classes

Every material claim uses one class. The classes stay separate.

| Class | Meaning |
|---|---|
| `DOCUMENTED` | An official page describes the behavior. |
| `SOURCE_INSPECTED` | A pinned public source shows the behavior. |
| `LOCAL_TESTED` | The authored offline checker or test exercised it. |
| `PROVIDER_ACTUAL` | An approved provider or chain call produced the result. |
| `NOT_RUN` | No evidence exists yet. |

A local success is `LOCAL_TESTED` at most. It cannot become `PROVIDER_ACTUAL` without an actual provider run under a separate released packet.

## Ownership and authority

Owned new paths: `docs/qualification/route-restrictions/` and `docs/implementation/ROUTE_RESTRICTIONS_PROFILE.md`. No application, shared document, migration, lockfile or configuration changed. This package selects no live network, no numeric production value, no credential and no provider. It grants no spending, signing, funding, broadcast, deployment or publication authority.
