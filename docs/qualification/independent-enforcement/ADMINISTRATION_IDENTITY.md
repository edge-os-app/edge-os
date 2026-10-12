# Administration, ownership and signer identity analysis

Task `POLICY-PREP-L3-20261012-01` v1, P21/P20/#58. Prepared 2026-10-12. Documentation and unsigned preparation only. This file selects and provisions no identifier. Every consequential value is a placeholder or a `REQUIRED_DECISION`.

Sources: `PV-CREATE`, `PV-WALLET`, `PV-SRV`, `PV-CS` (rechecked 2026-10-12); accepted P21 pins P7, P8, P10 and retained evidence R2. See [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md) and [../route-restrictions/SOURCE_EVIDENCE.md](../route-restrictions/SOURCE_EVIDENCE.md).

## 1. The identities in scope

| Identity | What it is | Who controls it | Effect |
|---|---|---|---|
| Application secret (`PRIVY_APP_SECRET`) | Authenticates the application to the Privy API. | The Edge OS service. | Can create and, for an **ownerless** policy, update the policy. |
| Application authorization key | A private key the service uses to sign API requests. | The Edge OS service. | Authenticates server-side requests. It is not the user's EVM key. |
| Policy-resource owner (`owner_id` of a policy) | The authorization signature required to modify the policy. Optional. | A user, a server key, or a key quorum. | When absent, the app secret alone can update the policy (PV-CREATE). |
| Wallet owner (`owner_id`, `user_id`, `public_key`, or key quorum) | Owns the wallet; can update the wallet's policies and signers. | The user (and any key quorum member). | A **satisfying** key-quorum member can update policies and signers while the user is offline (PV-SRV). |
| Additional signer (`signer_id`, a key quorum) | A signer added to a user-owned wallet, optionally with `override_policy_ids`. | The wallet owner authorizes the attachment. | Cannot change the wallet owner, its signers or its policies, and cannot export the key (R2). |
| Condition-set owner | Required to create a condition set; updates need an authorization signature (PV-CS). | Listed owner. | If `in_condition_set` is used, this is a second resource to separate. |

## 2. The exact control hypothesis

State the requirement as a set-intersection condition over the credentials the **executor** (the Edge OS execution service) holds:

> The executor credential set must be disjoint from every authority that can change policy content, signer attachments, overrides, the owner quorum, or wallet ownership. Formally: `executor_authorities ∩ {policy_owner, policy_owner_quorum, wallet_owner, wallet_owner_quorum, condition_set_owner} = ∅`, and the policy must have an explicit owner (so the app secret alone cannot update it).

Under this hypothesis, an allowed action can only happen inside the approved policy, and the executor cannot widen that policy. If the intersection is non-empty, the executor can weaken the policy and the independent control is not independent.

## 3. Why the executor cannot edit policy or grant authority (and where it can)

| Route to change policy or authority | Can the executor use it? | Condition | Source |
|---|---|---|---|
| Ownerless policy update | **Yes, if the policy is ownerless** — the app secret alone updates it. | Policy has no `owner_id`. | PV-CREATE, P8 |
| Owned policy update | Only if the executor is the policy owner or a satisfying member of the owner quorum. | Policy `owner_id` set and executor included. | PV-CREATE, P8 |
| Wallet policy/signer update | Only if the executor is a satisfying member of the wallet-owning key quorum. | Wallet owned by a quorum that includes the executor key. | PV-SRV, P10 |
| Additional-signer override | The executor signs under its own `override_policy_ids`. | Attachment must be authorized by the wallet owner. | PV-WALLET, P7, P9 |
| Additional signer changes owner/signers/policies | **No.** An additional signer cannot change the wallet owner, its signers or its policies, and cannot export the key. | Always. | R2 |
| Condition-set edit | Only if the executor is the condition-set owner. | `in_condition_set` used and the executor owns the set. | PV-CS |

Consequences:

- **Wallet ownership and policy-resource ownership are different.** A user-owned wallet with the application key only as an additional signer does **not** by itself separate policy administration, because an ownerless policy is still updatable with the application secret.
- The safe configuration needs **both**: (a) an explicit policy-resource owner outside executor control, and (b) a wallet owner quorum that does not include the executor key.
- The accepted offline module already records this. `PreparedPolicyRequest` carries `policy_owner_id` and `administration_separated`; `validate_binding` returns `POLICY_ADMIN_OWNER_MISSING` and `POLICY_ADMIN_NOT_SEPARATED` while they are absent. The default prepared request is ownerless, so it is a rule-body proposal only.

## 4. Required independent verification (before any attachment or signing release)

Each item is a bounded, separately approved provider check. None runs here.

1. **Policy owner present.** Read the policy resource; confirm `owner_id` is set and names a key quorum or key **outside** executor control. `REQUIRED_DECISION`: the owner identity and its exact public keys.
2. **App secret cannot change the policy.** A bounded provider attempt by the application secret to modify the policy must be denied (authorization failure), proving separation rather than assuming it.
3. **Wallet owner quorum excludes the executor.** Read the wallet `owner_id`; confirm the executor key is not a satisfying member.
4. **Executor is an additional signer with a restrictive override.** Confirm the executor `signer_id` and its `override_policy_ids` point at the restrictive policy, not a permissive one.
5. **Executor cannot raise its own authority.** A bounded attempt by the executor credential to change the wallet owner, add a signer, change a policy, or raise an allowance must be denied.
6. **Condition-set separation (if used).** If `in_condition_set` is used, confirm the condition-set owner is outside executor control.

Evidence class today: `NOT_RUN`. No provider call ran.

## 5. Blockers and unknowns

- **Owner and role configuration is a blocker.** The owner, role and current policy administration are `UNRESOLVED`. An unknown owner/role configuration blocks any actual test or funding. Do not proceed on an assumption.
- The deployed policy content hash is `UNSET`; it must be frozen and re-verified against the approved version before an action.
- The exact app-secret permission to modify policy resources is `UNVERIFIED` (see `docs/research/PRIVY_AND_AGENT_EXECUTION_PATTERNS.md`, "Remaining unknowns"). Separate administration and verify ownership before activation.
- Policy identity alone is insufficient; verify current policy **content**.

## 6. Placeholders (no identifier is selected here)

| Placeholder | Meaning | Status |
|---|---|---|
| `POLICY_OWNER_ID` | Policy-resource owner outside executor control | `REQUIRED_DECISION` |
| `WALLET_OWNER_QUORUM_ID` | Wallet-owning key quorum without the executor key | `REQUIRED_DECISION` |
| `EXECUTOR_SIGNER_ID` | Additional signer controlling the executor | `REQUIRED_DECISION` |
| `EXECUTOR_OVERRIDE_POLICY_ID` | Restrictive override policy for that signer | `REQUIRED_DECISION` |
| `POLICY_CONTENT_HASH` | Frozen hash of the approved policy content | `REQUIRED_DECISION` |
