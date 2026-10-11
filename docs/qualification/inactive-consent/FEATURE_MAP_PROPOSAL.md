# Inactive consent verification-map proposal

P26 inactive preparation. This is an owned proposal, not a change to the current
verify-edge-os browser map. The consent package is unwired: it exposes only Python
review/adopt/read seams and mounts no route. Naming the verifier does not prove its
browser journey covers this new module. The existing browser map stays unchanged.

## Public behavior and its check

| Public seam | Observable behavior | Owning check |
|---|---|---|
| `ConsentService.review` | Groups the exact revision/wallet/limits and saves an INACTIVE review | `tests/consent/test_grouped_review.py` |
| `ConsentService.adopt` | Persists one durable INACTIVE consent with exact identities | `tests/consent/test_adoption_durability.py` |
| `ConsentService.read_review` / `read_consent` | Owner-scoped readback; another owner sees nothing | both review/adoption test modules |
| Fail-closed denials | Stable denial codes saved; no affirmative consent | `tests/consent/test_grouped_review.py`, `test_adoption_durability.py` |
| Isolation | Accepted module rows unchanged | `tests/consent/test_isolation_inactive.py` |

## Proposed feature-map rows (not yet published)

| Feature | Behavior | Executable check | Evidence class |
|---|---|---|---|
| Inactive consent review | Exact grouped review, INACTIVE | `pytest tests/consent` | LOCAL_FIXTURE |
| Inactive consent adoption | Durable, idempotent, conflict-safe | `pytest tests/consent` | LOCAL_FIXTURE |

## Gaps (not covered by any browser or live path)

| Gap | Reason |
|---|---|
| API route | No router; the app mounts no consent endpoint. |
| UI / browser journey | No frontend component and no browser step exist for consent. |
| Production migration | The owned tables live only in the run-labelled test schema. |
| Real provider/signer/policy | Route and policy evidence is explicitly `UNQUALIFIED`. |
| Live activation | Deferred to qualified P20/P21/P24/P25 release evidence. |

Until a route and UI exist and a migration is published, the browser map must not
claim to cover this module. The local suite above is the only executable check.
