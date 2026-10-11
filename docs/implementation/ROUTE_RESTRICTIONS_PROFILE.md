# Route restrictions profile (local stage)

Owned package: `docs/qualification/route-restrictions/`. This profile records the local, offline restriction checks for the selected Kuru Flow fixed-input route (P21 #20). It is a qualification-preparation stage. It is not API/UI wiring, not production admission, not a provider call and not live execution.

Status: **decision profile prepared; runtime and provider enforcement unqualified.** The checker proves only that authored declarations preserve the stated relationships. It does not prove deployed bytecode identity, provider policy behavior, signing isolation, route support, transaction recovery or financial safety.

## Responsibility

The package evaluates one declared controlled action against one declared restriction profile. It answers: does this authored action satisfy every mandatory control, and is the profile ready to back a real action? It returns an offline verdict. A passing verdict is always `AUTHORED_FAKE_ONLY`.

The package is not independent wallet enforcement. It does not read, sign for, restrict or contact a real wallet, provider or chain.

## Files

| File | Responsibility |
|---|---|
| `restriction_checker.py` | Standard-library-only checker. Strict typed records, profile readiness, one-action evaluation. |
| `fixtures.json` | Authored fixtures: an all-enforced positive control, one-field adversarial cases, a truthful route profile and a missing-control profile. |
| `test_restriction_checker.py` | Offline unit tests, including the no-network/no-signing property and malformed-declaration controls. |
| `capacity_examples.py`, `test_capacity_examples.py` | Independent capacity arithmetic and its tests. |
| `VERIFICATION_MAP_PROPOSAL.md` | Local verification and future live-verification proposal. |
| `README.md`, `SOURCE_EVIDENCE.md`, `NETWORK_DECISION.md`, `CONTROL_RESTRICTIONS.md`, `WORKED_CAPACITY.md`, `LIVE_TEST_PACKET.md` | Preparation documents. |

Names describe responsibility. The ticket number is not a module name.

## Public interface

- `evaluate_declared_case(profile, action) -> CaseVerdict`
- `profile_readiness_reasons(profile) -> tuple[str, ...]`
- `load_profile(mapping) -> RestrictionProfile`
- `load_action(mapping) -> ControlledAction`

`RestrictionProfile` holds one `ControlDeclaration` per mandatory control: `state` (`ENFORCED`/`UNSUPPORTED`/`UNKNOWN`/`UNSET`), `layer` (`HOST`/`CONTRACT`/`INDEPENDENT_POLICY`) and `evidence` (`DOCUMENTED`/`SOURCE_INSPECTED`/`LOCAL_TESTED`/`PROVIDER_ACTUAL`/`NOT_RUN`).

`ControlledAction` carries the action plus its authored approval bounds. The adopted bindings are `approved_networks`, `approved_entrypoints`, `approved_signers`, `approved_assets`, `approved_methods`, `approved_recipients`, `approved_input_raw`, `approved_program_hex`, `approved_fee_bps`, `approved_referrer_fee_bps`, `approved_fee_collectors`, `approved_referrers`, `approved_is_in_token_fee` and `approved_allowance_raw`. Each action value must match its adopted binding. Fee values, fee recipients, fee mode, allowance, input age, intent expiry and mandate expiry are explicit or unknown.

`CaseVerdict` reports `accepted`, `result_class` (`AUTHORED_FAKE_ONLY` or `BLOCKED`) and the ordered, de-duplicated `reasons`.

## Mandatory controls

Twelve mandatory controls gate a real action: `chain`, `wallet_signer_binding`, `entrypoint_method`, `input_output_assets`, `raw_input`, `recipient`, `minimum_output`, `fees`, `approvals`, `gas_action_capacity`, `expiry_freshness`, `opaque_program`. The full matrix is in `CONTROL_RESTRICTIONS.md`.

## Fail-closed rules

- A missing mandatory control returns `MISSING_MANDATORY_CONTROL:<name>`.
- A control that is `UNSUPPORTED`, `UNKNOWN` or `UNSET` returns `UNSUPPORTED_CONTROL:<name>`.
- A control marked `ENFORCED` with `NOT_RUN` evidence returns `EVIDENCE_MISSING:<name>`.
- The action must match its adopted bindings: network, entrypoint, signer, method, assets and decimals, recipient, exact input, route program, fee value, fee-collector address, referrer address, input/output fee mode, and owner allowance.
- An absent, empty or whitespace-only applicable actual identity returns the control's not-allowed reason, independently of membership. An adopted identity set or asset map with an empty or whitespace entry returns `ADOPTED_IDENTITY_INVALID`. A zero fee keeps its collector or referrer inapplicable.
- Amounts are canonical unsigned base-10 strings that match the whole value. Boolean, float, negative, leading-zero and trailing-character raw values are rejected.
- The route program must be present, hex and at least one byte.
- An unknown required value (gas, gas used, action capacity, quote age, input age, fee, allowance, evaluation time, intent expiry, mandate expiry) is not zero and blocks the action. An unknown quote returns `QUOTE_UNKNOWN`.
- The minimum received must exist, and must not exceed the quote.
- `feeBps + referrerFeeBps <= 10000`.
- A local case that claims a non-local result class returns `EVIDENCE_UNMATCHED`.
- A malformed declaration (non-integer or negative fee/capacity/age, non-string identifier or allow-list item, non-integer asset decimal, empty profile version or action identity) raises a field-specific `ValueError`. The loader never coerces these values. The default command reports it as `error: ...` and exits non-zero.

## Enforcement boundary

| Layer | Contract obligation | Status and next qualification |
|---|---|---|
| `HOST` | Derive identity; bind owner/agent/wallet/network/strategy/mandate; check expiry and freshness; hold reservations. | Written behavior only. P22 must test actual state and denial. |
| `CONTRACT` | Enforce input token, exact input, minimum received after fees, fee bound, recipient and approval handling. | Source-inspected from the pinned public source. Deployed equivalence `UNKNOWN`. |
| `INDEPENDENT_POLICY` | Independently restrict network, contract, method and ABI-decoded arguments. | Config-dependent. Policy support for decoded arguments is documented; bounds on opaque `bytes` stay `UNKNOWN`. |
| Position inventory | Cover attributable inventory and prevent double sale. | Requires live proof. The application ledger is not provider verification. |

A control that is unenforceable at the selected layer keeps the affected real action unavailable. A new approver, contract wrapper or changed authority architecture is a material builder decision.

## Evidence classification

All results here are `LOCAL_TESTED` at most, over authored synthetic approvals and holdings. They are not provider enforcement and not live wallet inventory. Provider and chain results stay `NOT_RUN`. This complements the P22 admission profile; it does not replace it.

## Run the offline checks

From the repository root:

```sh
python3 -B -m unittest discover -s docs/qualification/route-restrictions -p 'test_*.py' -v
python3 -B docs/qualification/route-restrictions/restriction_checker.py
```

The checker loads no environment values, credentials, provider data or network connection. The test suite asserts that the checker's imports are offline-only and that the default command reports `provider_executed: NOT_RUN`.

## Boundaries

- Local fixture work only. Live admission stays closed until P21 and the operational gates pass.
- No application wallet, provider client, signing path or live command exists in this stage.
- No API route, UI, migration, lockfile or shared configuration is added.
- The package references P15/P16/P20 and the P22/P23/P24/P25/P26/P30 stages. It does not claim their implementation exists.
- Full P21 issue #20 stays OPEN and unqualified beyond this proved preparation.
