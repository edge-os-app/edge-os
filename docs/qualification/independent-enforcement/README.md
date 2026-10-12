# Independent enforcement preparation

Task `POLICY-PREP-L3-20261012-01` v1, P21/P20/#58, GitHub issue #20. Worker pane `%7`. Base `c9a6ac83dbb686dd744ca093c05f6932639df54c`, branch `ticket/policy-enforcement-prep`. Prepared 2026-10-12.

Stage: **documentation and unsigned preparation only.** This package resolves what the current documented independent controls can express for the selected Kuru Flow route and prepares the exact, separately approvable provider test packet. Actual enforcement stays `NOT_RUN`.

It runs no provider request, creates no wallet, claims no faucet, signs nothing, broadcasts nothing and changes no policy. Full P21 stays `OPEN`.

## Verdict

- **DOCUMENTATION / PREPARATION: PASS within this scope.** The capability matrix maps each mandatory control to a source-backed independent-layer class. The administration analysis pins the owner/signer separation requirement. The worked vectors cover the positive and adversarial cases. The qualification packet is a concrete `NOT_RUN` proposal.
- **Independent enforcement: `NOT_RUN`.** No provider call ran. The opaque `program` byte equality, the tuple-component calldata paths and the deployed `143` bytecode identity stay `UNKNOWN`. Position inventory stays `UNSUPPORTED` at the independent layer.
- **Boundary-only feasibility `PASS` may be accepted while actual enforcement is `NOT_RUN`.** A local `AUTHORED_POLICY_ALLOW` is never `PROVIDER_ACTUAL`.

## Documents

- [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) - the control-by-control independent-policy matrix and the exact units/ABI/decode/case/default-deny semantics.
- [ADMINISTRATION_IDENTITY.md](ADMINISTRATION_IDENTITY.md) - the owner, signer and policy-content identities and the executor-separation hypothesis.
- [WORKED_CASES.md](WORKED_CASES.md) and [worked_vectors.json](worked_vectors.json) - the unsigned positive and adversarial cases and the bounded machine vectors.
- [QUALIFICATION_PACKET.md](QUALIFICATION_PACKET.md) - the `NOT_RUN` qualification packet with `REQUIRED_DECISION` labels.
- [LANE2_INTEGRATION.md](LANE2_INTEGRATION.md) - the #58 and P20 consumption map and the remaining financial gates.
- [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md) - the 2026-10-12 source recheck, URLs, sections and pins.

## Reused accepted work

- [`../route-restrictions/`](../route-restrictions/) - the accepted P21 restrictions package (README, CONTROL_RESTRICTIONS, SOURCE_EVIDENCE, NETWORK_DECISION, LIVE_TEST_PACKET, PRIVY_POLICY_BINDING_FEASIBILITY, POLICY_BINDING_INTEGRATION_NOTE, WORKED_CAPACITY).
- `docs/qualification/p16/PROVIDER_SIGNING_RESULT_2026-10-08.md` - bounded testnet `10143` sign-only evidence.
- `docs/research/PRIVY_AND_AGENT_EXECUTION_PATTERNS.md` - private research; Assensus X Layer proof is a pattern only.
- `edge_os_api.kuru_flow.policy_binding` - the accepted offline binding module (not edited).

## Run the existing offline checks

From the repository root:

```sh
python3 -B -m unittest discover -s docs/qualification/route-restrictions -p 'test_*.py' -v
python3 -B docs/qualification/route-restrictions/restriction_checker.py
python3 -B docs/qualification/route-restrictions/capacity_examples.py
(cd apps/api && uv run --frozen pytest tests/kuru_flow -q)
```

This package adds no test. It reuses the accepted checks and records the result in the worker result.

## Ownership and authority

Owned new paths: `docs/qualification/independent-enforcement/` only. No application, shared document, migration, lockfile or configuration change. This package selects no live network, no numeric production value, no credential and no provider. It grants no spending, signing, funding, broadcast, deployment or publication authority.
