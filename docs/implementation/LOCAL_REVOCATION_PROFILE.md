# Local revocation profile (local stage)

Owned package: `apps/api/src/edge_os_api/revocation/`. This profile records the
local removal domain for P30 #40. It is the approved 2026-10-10 release portion
only: **preparation**. It is not API/UI wiring, not a production migration, not
signer removal at a live provider and not live qualification.

## Responsibility

The package records an owner's removal request for one selected agent wallet,
reconciles controlled provider-style observations against that original request,
and derives a truthful local state (`NOT_REQUESTED`, `REQUESTED`, `PENDING`,
`UNKNOWN`, `CONFIRMED`, `FAILED`). A pending, unknown or confirmed removal denies
a new agent submission through a NEW local check. A local record is not confirmed
provider removal, and a local stop never substitutes for provider removal.

It writes only its own `revocation_local` tables. It never writes holdings,
allowances, reservations, claims, recovery cases, funding flows, stops, inactive
consent or a wallet binding. It cancels no broadcast action and releases no
reservation.

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Strict typed models: states, request, observation, view, provenance; identifiers and times validated at the boundary. |
| `records.py` | Owned SQLAlchemy tables on `RevocationBase`, in the `revocation_local` schema. |
| `removal_service.py` | `RemovalService`: request, reconcile, read and the derived-state read; owner resolution, binding resolution and the per-wallet advisory lock. |
| `enforcement.py` | The NEW local P30 submission-denial seam, prepared and **unwired**. |

Application names describe responsibility. The ticket number is not a module name.

## Verified-owner rule

Every `RemovalService` call receives `verified_owner_id` from the caller's
verified identity. A `RemovalRequest` or `RemovalObservation` never carries an
owner; `extra="forbid"` rejects one at the boundary. Retrieval is owner-scoped;
another owner sees the same result as a missing record. The service resolves the
actual saved agent/wallet/network through the accepted saved `wallet_setups`
binding (a read-only owner-scoped read), not from a caller field.

## Request seam

`request_removal(verified_owner_id, RemovalRequest)`:

- resolves the current `CONFIRMED` wallet binding for the requested agent and
  network; a missing binding is refused;
- refuses a supplied `expected_wallet_id` that disagrees with the saved binding;
- takes the shared per-wallet advisory lock, then re-reads the binding under the
  accepted `wallet_setups` `FOR UPDATE` row lock (the same lock the accepted
  wallet setup writer uses) and holds it through commit, so a concurrent binding
  change cannot commit between the validation and the durable write;
- persists the request (identity, reason, evidenced signer/policy, provenance,
  requested time) before any controlled effect;
- is idempotent on an exact repeat (same request key and the same material
  content returns the same durable record) and refuses any changed reuse (a
  different request key, signer, policy or reason) for the same removal identity.

The derived state after a request is `REQUESTED`. No rebinding, reactivation or
clear operation exists in this stage.

## Observation reconciliation

`reconcile(verified_owner_id, RemovalObservation)` keeps the owner request, the
provider-style observation and the derived state separate. It takes the shared
per-wallet advisory lock, locks the request and state rows, and re-reads the
current binding under the accepted `wallet_setups` `FOR UPDATE` row lock (held
through commit) in the same transaction. An exact repeated observation key with
the same material content is idempotent: the recorded outcome of that observation
(its accepted or denial status and the derived state and reason it produced) is
returned, not the later derived state, and nothing is replayed. A changed reuse of
the same observation key is refused with a stable error. An observation is refused,
and recorded with a stable denial code, when:

- the current wallet binding is missing or no longer matches the request
  (`STALE_WALLET_BINDING`);
- the observed agent, wallet or network does not exactly match the request
  (`OBSERVATION_IDENTITY_MISMATCH`);
- the observation is older than the current state (`STALE_OBSERVATION`);
- the observed signer or policy contradicts the request (`WRONG_SIGNER`,
  `WRONG_POLICY`).

A matched observation derives its state. Only a `CONFIRMED` observation **with
evidenced signer or policy identity** produces `CONFIRMED`; when neither the
request nor the observation evidences a signer or policy, the derived state stays
`UNKNOWN` (`SIGNER_EVIDENCE_UNKNOWN`) rather than fabricating confirmation. A
`PENDING`, `UNKNOWN` or `FAILED` observation derives that state. Once `CONFIRMED`,
the removal is sticky: a later observation that does not re-confirm the exact same
evidenced target, including one that omits the signer or policy evidence, is
retained as contradictory (`contradictory = true`) and neither restores removed
permission nor replaces the confirmed signer. Every observation is append-only and
auditable.

## Derived state and the local P30 check

`submission_denial(session, verified_owner_id, agent_id, wallet_id, network_id)`
reads the persisted derived states inside the caller's transaction and returns
the stable reasons for a `PENDING` (`REMOVAL_PENDING`), `UNKNOWN`
(`REMOVAL_UNKNOWN`) or `CONFIRMED` (`REMOVAL_CONFIRMED`) removal. `REQUESTED`,
`FAILED` and absent records do not deny.

The check reads only `revocation_local`. It never reuses a stop token and never
treats a stop or an exhausted allowance counter as provider removal.

## Unwired boundary

The local P30 check is prepared but **NOT mounted**. No accepted P22 admission or
P23 execution caller consults it in this stage (`enforcement.P30_CHECK_WIRED` is
`False`). The missing connection is recorded for future qualified wiring. This
package must not claim that typed denials already block a live submission path.

## Authority and qualification boundary

A local record is not a live provider operation and not an independent Privy
proof. The provider-style observations in the tests are authored fixtures labelled
`SYNTHETIC_AUTHORED`. The package performs no provider call, signing, wallet or
policy change, funding, broadcast, deployment or publication. Final P30 acceptance
requires the later qualified P20 and P26 release evidence. A local stop stays
distinct from provider removal; a local removal cannot cancel a broadcast
transaction or release its reservations.

## Integration update (#58, 2026-10-12)

The local-stage statements above record the preparation history. In the #58 connected candidate the `revocation_local` schema ships in migration 0008, `revocation/routes.py` mounts request, read and reconcile, and the check is wired (`P30_CHECK_WIRED = True`) through `SubmissionControls` at admission and at submission ownership under the shared wallet lock. `REQUESTED` now denies (`REMOVAL_REQUESTED`) because the request is saved before any provider effect; the earlier statement that `REQUESTED` does not deny describes the preparation stage only. See `USER_RELEASE_INTEGRATION_PROFILE.md`. Fixture evidence only; live qualification stays NOT_RUN.
