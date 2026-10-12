# P08 Investigation Adoption Runtime Profile

## Behavior

An owner may review and save a bounded investigation declaration for an `INVESTIGATE_EFFECT` request. The request remains unchanged. If the request has no interpretation revision, the proposal and saved declaration bind to `null`; the original text is still retained. Every required configuration field and the EdgeSpec must have a source, origin and explicit `ADOPTED` status.

The declaration, proposal and budget use the version-2 contract. Claims must have one compatible meaning: a `HYPOTHESIS` has `DECLARED` falsification and `OUTPERFORM` or `UNDERPERFORM` direction; `DESCRIPTIVE_ONLY` has descriptive falsification and `DESCRIPTIVE` direction. The API enforces this even when a caller bypasses the UI.

The proposal is fixture-only and visibly unqualified. It sets the maximum cost to `$0`, limits access to `FIXTURE_ONLY`, marks optional creator, wallet and social tools unavailable, and gives no provider or execution permission. The review includes the question, pool limitations, variants, direction, positive integer outcome horizons with explicit units, sources, candidate/parameter/compute limits, UTC period, partition membership boundaries, stop rule, exact budget version, claim, falsification condition, alternatives and explicit unknowns. Descriptive work declares one partition covering the complete period and no invented holdout. Predictive work declares bounded training, validation and holdout intervals. Intervals stay within the declared period, are ordered and cannot overlap.

Each adopted evaluation identity maps to exactly one explicit plan row containing its trial identity, variant identity, horizon and partition identities. Every trial is referenced, every row is included in the evaluation budget, and no Cartesian product or extra evaluation is implied. The plan itself is explicitly user-confirmed. Original request words remain unchanged even when a bounded proposed value uses a supported structured representation. Unknown participant identity/incentives, persistence/capacity, costs and evidence coverage remain unknown until supported.

Saving appends an immutable `InvestigationDeclaration` and its initial `DECLARATION_SAVED` access event in one transaction. Both state that outcome labels were not read; the access event records zero provider queries and no study start. Saving does not execute a study. A new hypothesis receives a new `edge_id`; a revision must point to an owner- and request-scoped parent, preserve its edge identity and increment the version. Idempotent retries return the saved identities.

Clarification and new declaration saves lock the same owner-scoped intake row before re-reading the current interpretation head. A concurrent clarification therefore either commits first and makes a new stale save fail, or waits until a current save commits. A committed matching operation/key/body is replayed before mutable head checks, so a lost response can recover the original identity after a later clarification. Non-NFC review text is rejected at the request schema with a field-specific validation error; the frozen P02 canonicalizer is unchanged.

## Routes and records

- `GET /v1/research/requests/{intake_id}/investigation-proposal` retrieves the current owner-scoped, unadopted proposal.
- `POST /v1/research/requests/{intake_id}/investigations` validates and saves an adopted declaration.
- `GET /v1/research/requests/{intake_id}/investigations` lists only that owner's declarations and access events.
- `GET /v1/research/requests/{intake_id}/investigations/{declaration_id}` reopens one exact declaration and access event.
- `investigation_declarations` and `investigation_access_events` have owner/request foreign keys and reject updates and deletes.

## Verification

Focused API coverage is in `apps/api/tests/test_investigation_adoption.py`; UI adoption/reopen coverage is in `apps/web/tests/investigation-review.test.tsx`. The end-to-end P03 harness also drives P08 on desktop and 390px mobile, inspects actual database rows, denies cross-owner list/read/adoption, restarts the API and reopens the exact declaration in a new browser context. `.agents/skills/verify-edge-os/feature-map.md` records the route, SQL fields and retained evidence.

## Limits

This profile uses only an unqualified synthetic fixture. It does not qualify a research pool, make provider calls, inspect outcomes, run an investigation, create a strategy, or access a wallet. Numeric limits and provider policy remain unresolved for any future adopted run. The declaration is not P09 outcome-read authorization.

## #58 Task 6 extension: recorded-history declarations (`p08.investigation-declaration/3`)

Version 2 is unchanged. Version 3 declarations are saved by `POST /v1/research/requests/{id}/history-investigations` in the same `investigation_declarations` table, before any collection, with frozen configuration, rule-map and source-profile hashes. Version 2 reads and the P09 fixture run ignore them. Rules must be `USER_ADOPTED`; worked-example rules are refused. Details and limits: `USER_RELEASE_INTEGRATION_PROFILE.md`, section "Task 6 local implementation".
