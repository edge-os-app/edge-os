# Lane 2 integration note

Task `POLICY-PREP-L3-20261012-01` v1, P21/P20/#58. Prepared 2026-10-12. Preparation only. It changes no application composition.

This note maps how lane 2 (#58 application composition) and the future P20 integrated packet consume this preparation, and which financial gates remain separate. It adds no wiring, route, scheduler or provider call.

## 1. What lane 2 consumes

| Source | Consumed by | Use |
|---|---|---|
| [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) | #58, P20 packet | Which controls are `DOCUMENTED`, `UNKNOWN` or `UNSUPPORTED` at the independent layer. |
| [ADMINISTRATION_IDENTITY.md](ADMINISTRATION_IDENTITY.md) | #58, P20 packet | The policy-owner and wallet-owner separation requirement. |
| [WORKED_CASES.md](WORKED_CASES.md) + [worked_vectors.json](worked_vectors.json) | P20 packet | The independent denial-harness case list and the local-versus-independent verdict split. |
| [QUALIFICATION_PACKET.md](QUALIFICATION_PACKET.md) | Builder + P20 packet | The `NOT_RUN` release proposal and its `REQUIRED_DECISION` placeholders. |
| [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md) | #58, P20 packet | The 2026-10-12 recheck of the primary sources. |

## 2. Module and import path (unchanged)

- Package: `edge_os_api.kuru_flow.policy_binding`.
- Public functions: `build_policy_request`, `validate_binding`, `facts_from_decoded_call`, `evaluate_authored_policy`.
- The package uses relative imports to its parent adapter package; the adapter's offline test asserts that no file outside the adapter directory references the adapter package name. Keep this import style in later edits.
- This preparation adds **no** application, route, migration, lockfile or configuration change.

## 3. Required caller behaviour (unchanged, restated)

1. Call `validate_binding`. While it returns any reason, the request is incomplete and the affected real action stays closed. Do not weaken the reason set to get a pass.
2. Treat `evaluate_authored_policy` as authored behaviour only. Never surface its result as an independent provider restriction.
3. Bind the transaction value to the actual native value or to `0` for an ERC-20 input. It is separate from the calldata token notional.
4. Bind an explicit policy-resource owner outside executor control. An ownerless policy is updatable with the application secret alone.
5. Bind the request to the exact wallet, network, entrypoint, method and adopted values. A changed configuration needs a fresh request.

## 4. Preserved policies

- **Original action identity.** The adapter candidate identity anchors the original action. Recovery and restart preserve it; no duplicate and no replacement route.
- **Current-holdings reconciliation.** Record the input balance, output balance and native gas before the action. Different asset IDs are never summed. A confirmation consumes actual entry gas and keeps the retained exit hold.
- **Expiry policy.** The Flow intent has no on-chain deadline. Local intent and mandate expiry live at `HOST`; they cannot revoke a broadcast. No calldata time condition is documented.
- **Residual exposure.** Unknown liability is never zero. Record remaining holdings or resting exposure and its separate cancellation authority.

## 5. Remaining financial and integration gates (separate authority)

| Gate | Owner | State |
|---|---|---|
| Policy attachment and update | Builder + policy owner | Not requested |
| Wallet signer attachment / removal | Wallet owner | Not requested |
| Funding the agent wallet | Builder | Not requested |
| Signing and broadcast | The selected transport | Not requested |
| Provider denial harness | Builder (isolated release) | Not requested |
| Mainnet `143` exact-risk approval | Builder | Not requested |
| PR, merge to `main`, publication | Builder + controller | Not requested |

## 6. P27 dependencies

- P31 health and conversation agreement is a **P27 dependency**. It is queued separately after this lane-3 preparation is accepted and safely released. There is no P31 implementation or scheduler now.
- The future P20 integrated packet depends on P22 (local admission), P23 (durable intent and exclusive claim), P24 (recovery), P25 (stop) and P26/P30 (consent/removal preparation). This note **references** them; it claims none of them exists.

## 7. Lane 2 ownership boundaries

Lane 2 owns the shared API, auth, settings, database, migrations, usage, UI, application worker and verifier mounting. This preparation changes none of those. The independent-enforcement documents are new paths under `docs/qualification/independent-enforcement/` only.

## 8. Verdict

A boundary-only feasibility `PASS` may be accepted while actual enforcement stays `NOT_RUN`. This note does not prove an independent provider restriction and does not approve any live action.
