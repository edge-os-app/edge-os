# Local revocation verification-map proposal

P30 local preparation. This is an owned proposal, not a change to the current
verify-edge-os browser map. The revocation package is unwired: it exposes only
Python request/reconcile/read and denial seams and mounts no route. Naming the
verifier does not prove its browser journey covers this new module. The existing
browser map stays unchanged.

## Public behavior and its check

| Public seam | Observable behavior | Owning check |
|---|---|---|
| `RemovalService.request_removal` | Persist one durable owner removal request before any effect; idempotent; conflict on changed reuse | `tests/revocation/test_request_records.py` |
| `RemovalService.reconcile` | Derive real states; exact-match fixture confirmation; refuse bad observations; keep contradictions auditable | `tests/revocation/test_reconcile_state.py` |
| `RemovalService.read_removal` | Owner-scoped readback; another owner sees nothing | `tests/revocation/test_request_records.py` |
| `RemovalService.submission_denial` | NEW local P30 check denies pending/unknown/confirmed | `tests/revocation/test_enforcement.py` |
| Accepted-row preservation | Admission, stop, funding, consent and wallet rows unchanged | `tests/revocation/test_preservation.py` |
| Durability and process race | Confirmed removal survives a new process; concurrent requests serialize | `tests/revocation/test_durability.py` |

## Proposed feature-map rows (not yet published)

| Feature | Behavior | Executable check | Evidence class |
|---|---|---|---|
| Local removal request | Durable owner request, pre-effect, idempotent | `pytest tests/revocation` | LOCAL_FIXTURE |
| Local removal reconciliation | State derivation, exact-match confirmation, refusals | `pytest tests/revocation` | LOCAL_FIXTURE |
| Local P30 denial check | Denies pending/unknown/confirmed (UNWIRED) | `pytest tests/revocation` | LOCAL_FIXTURE |

## Gaps (not covered by any browser or live path)

| Gap | Reason |
|---|---|
| API route | No router; the app mounts no removal endpoint. |
| UI / browser journey | No frontend component and no browser step exist for removal. |
| Production migration | The owned tables live only in the run-labelled test schema. |
| Real provider signer removal | Observations are authored fixtures; no provider call is made. |
| P22/P23 wiring | The local P30 check is prepared and unmounted (`P30_CHECK_WIRED = False`). |
| Live/final acceptance | Deferred to the later qualified P20 and P26 release evidence. |

Until a route and UI exist, a migration is published and the check is wired, the
browser map must not claim to cover this module. The local suite above is the only
executable check.
