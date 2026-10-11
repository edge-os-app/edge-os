# Inactive consent local verification record

P26 inactive preparation. Every result below is local application behavior under
authored synthetic terms, approvals and fixtures. It is not provider, chain,
wallet or financial evidence. The owned tables live in `consent_local` inside the
run-labelled test database only.

## Check matrix

| Accepted check (issue 38 / packet) | Source inspected | Harness executed | Status |
|---|---|---|---|
| Group the exact revision, rules, evidence and limitations, wallet/network/route, allocation, per-asset allowances, attempts, gas, expiry and stop effects | Spec `StrategySpec`, `ExecutionMandate`; P06 profile; P15 contract; `types.py`, `grouped_review.py` | `tests/consent/test_grouped_review.py` | PASS, authored fixtures |
| Balance is not allocation; historical success is not compulsory; model/memory text is not authority | Spec §"Accepted activation" and "Live trading" | `test_wallet_balance_is_shown_separately_from_allocation` | PASS, authored fixtures |
| Accept trusted verified identity; another owner or unselected agent cannot read or adopt | P15 verified-owner rule; P01 auth profile | `test_another_owner_cannot_review_or_read_the_revision`, `test_another_owner_cannot_adopt_or_read_the_consent` | PASS, authored fixtures |
| Keep wallet/network/revision identity exact and immutable; never substitute the latest revision | P06 revision identity; P17 binding | `test_review_groups_the_exact_selected_revision_wallet_and_limits`, `test_a_foreign_revision_is_indistinguishable_from_a_missing_one` | PASS, authored fixtures |
| Persist explicit owner adoption with exact content identities as a clearly INACTIVE consent | Issue 38 release deliverable | `test_adopt_returns_clearly_inactive_consent_with_exact_identities` | PASS, authored fixtures |
| All outcomes inactive; no activation/signing/admission/scheduler/provider-policy operation; no active authority snapshot | Packet owned boundary | all owned tests assert `status == "INACTIVE"` and the module exposes only review/adopt/read | PASS, authored fixtures |
| Refusal saves no affirmative consent | Packet refusal rule | `test_stale_review_hash_is_denied_and_saves_no_consent`, `test_expired_terms_are_denied`, drift tests | PASS, authored fixtures |
| Stale/mismatched revision/wallet/network/terms, changed terms, absent/invalid limits, expired terms and drifted bindings are denied | Packet denial list | `test_mismatched_network_wrong_network_asset_and_wallet_revision_are_denied`, `test_changed_terms_for_the_same_revision_conflict`, `test_expired_terms_are_denied`, `test_revision_drift_after_review_denies_adoption`, `test_wallet_drift_after_review_denies_adoption` | PASS, authored fixtures |
| Missing/unknown versus zero, Boolean/integer coercion, asset units, malformed/blank identifiers, negative/non-finite amounts | Packet failure checks | `tests/consent/test_types_validation.py` | PASS, authored fixtures |
| Identical repeated adoption idempotent; changed reuse conflicts; concurrent/stale/rollback/lost-response safety; durable exact readback in a new process | Packet atomicity check | `test_repeated_adoption_is_idempotent`, `test_concurrent_adoption_yields_one_consent`, `test_true_process_reopen_reads_the_durable_consent` | PASS, authored fixtures |
| Consent records/reads change no holdings, allocation, consumed allowances, reservations, claims, pending recovery, stop history, breach state or another agent; cannot reset or raise a budget | Packet isolation check | `tests/consent/test_isolation_inactive.py` | PASS, authored fixtures |
| API route, UI, production migration | Packet boundary | none | NOT_RUN |
| Real provider, signer/policy binding, live route, full P26 activation | Packet boundary | none | NOT_RUN |

`HARNESS_EXECUTED` means the owned pytest suite ran against the run-labelled
PostgreSQL 18 container. `NOT_RUN` means no such operation exists or ran in this
stage. A harness PASS does not imply an API, provider or activation PASS.

## Raw receipts

The owned suite is the raw receipt. It writes the repository's standard pytest
evidence (`P03_EVIDENCE_DIR`, default `.scratch/p03/evidence/pytest`) and asserts
resource cleanup. The command, candidate identity and full-run timing are recorded
in the worker's `.scratch/smux-release-next/p26/evidence/` submission packet.

## Limits

- The reviewed terms are authored (`SYNTHETIC`). They are not a numeric product
  mandate, a policy binding or a provider configuration.
- The route and policy qualification stay `UNQUALIFIED`; no live gate is claimed.
- The true-process reopen proves durable storage readback, not a distributed
  exactly-once guarantee.
