# Policy binding integration note for #58 and P20

Task `P21-POLICY-L4-20261012-01` v1. Prepared 2026-10-12. This note is preparation only. It changes no application composition. Full P21 stays OPEN.

The interface note is for the future P20 integrated packet and for ticket #58. Full application composition stays with #58. This note does not add wiring, a route, a scheduler or a provider call.

## Module and import path

- Package: `edge_os_api.kuru_flow.policy_binding`.
- Public functions:
  - `build_policy_request(config, *, wallet_id, policy_name=..., rpc_method=...) -> PreparedPolicyRequest`
  - `validate_binding(prepared) -> tuple[str, ...]`
  - `facts_from_decoded_call(*, chain_id, entrypoint_address, rpc_method, call) -> PolicyFacts`
  - `evaluate_authored_policy(request, facts) -> PolicySimulationVerdict`
- Public types: `PreparedPolicyRequest`, `PolicyRequest`, `PolicyRule`, `PolicyCondition`, `PolicyFacts`, `PolicySimulationVerdict` and the enums.

The package uses relative imports to its parent adapter package. The adapter's own offline test asserts that no file outside the adapter directory references the adapter package name. A relative import keeps that assertion true. Keep this import style in later edits.

## What each caller does

| Caller | Responsibility |
|---|---|
| P20 packet (future, released) | Convert the prepared request into an exact provider policy, submit a positive control and an independent denial control, and record the provider result. |
| #58 (application composition) | Convert an approved `ApprovedAdapterConfiguration` into a prepared request, attach the policy to the user-owned wallet, and route denial and recovery. |
| This package | Build, validate and locally simulate the declared request only. It never submits. |

## What stays unchanged

- No application, route, migration, lockfile or configuration change.
- The adapter package (`kuru_flow/`) is unchanged except for the new subpackage.
- No new enforcement architecture. No route substitution.
- The package selects no live value, no credential and no provider.

## Required caller behavior

1. Call `validate_binding`. While it returns any reason, the request is incomplete and the affected real action stays closed. Do not weaken the reason set to get a pass.
2. Treat `evaluate_authored_policy` as authored behavior only. Never surface its result as an independent provider restriction.
3. Keep the policy administrator separate from the executor key. Do not put the application authorization key in the wallet-owning key quorum (see [PRIVY_POLICY_BINDING_FEASIBILITY.md](PRIVY_POLICY_BINDING_FEASIBILITY.md#3-policy-ownership-and-update-authority)).
4. Bind the request to the exact wallet, network, entrypoint, method and adopted values. A changed configuration needs a fresh request.

## Unresolved inputs for #58/P20

- Exact `program` byte equality at the provider: `UNKNOWN`.
- Tuple-component calldata path support: `UNKNOWN`.
- Deployed mainnet bytecode identity against the pinned source: `UNKNOWN`.
- Testnet Flow support: not documented.
- Policy administration separation proof: `NOT_RUN`.

Any unresolved mandatory input keeps the affected capability closed. The builder selects the consequential live configuration.

## Changed source claims

This package adds a policy-binding feasibility claim from new Privy sources. It does not change the accepted route-restriction findings. The `opaque_program` control stays the limiting control and stays `UNKNOWN` at the independent layer. The `position_inventory` restriction stays `UNSUPPORTED` there. Earlier verdicts and history are preserved in [README.md](README.md), [CONTROL_RESTRICTIONS.md](CONTROL_RESTRICTIONS.md) and [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md).
