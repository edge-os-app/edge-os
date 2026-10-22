# Stage B: Privy signers on judges' embedded wallets (research facts)

Task `CLOUD-B-RESEARCH`, builder-approved normal cloud session, 2026-10-23. Base `origin/integration/edge-os-mvp` at
`82290e203982ee710189c4d983edce9a4ddfba9f`. Status `RESEARCH`. This file approves no policy change, signer attachment,
wallet change, funding, signing or broadcast. No Privy API call, account, key or payment was used.

Stage B: a judge signs in, adds our app's key quorum as a signer on their own Privy embedded wallet, and attaches our
builder-owned policy to that signer. Our worker then signs inside those limits through
`apps/api/src/edge_os_api/execution/privy_signer.py` (`eth_signTransaction`, P-256 authorization signature).

## Labels and source access

- **FACT**: stated in the cited source, with a quote.
- **INFERENCE**: our conclusion, with the reasoning given.
- **UNKNOWN**: not settled by any source available here. The smallest live check that would settle it is given.

The network policy of this session refused every connection to `docs.privy.io`, its Mintlify mirror and `privy.io`
(proxy `connect_rejected`, HTTP 403 on CONNECT). The sources are therefore of three kinds:

1. **SDK source** (primary). Published npm tarballs, unpacked and read locally. A reader can reproduce each quote with
   `npm pack <package>@<version>` and the in-package path given. Integrity values come from `npm view <pkg>@<ver> dist.integrity`.
2. **Docs (search index)**. Text that a web-search index returned for the cited `docs.privy.io` URL. The page itself
   could not be opened here, so these quotes are as the index returned them. Re-read the page before a live decision.
3. **Repository evidence**. Earlier verified documents and live results in this checkout.

`help.privy.com` and `privy.com` belong to a different company (Privy, the e-commerce marketing tool). Nothing here
relies on them.

### SDK packages read

| Package | Version | Published | `dist.integrity` |
| --- | --- | --- | --- |
| `@privy-io/react-auth` | 3.51.0 | 2026-10-21 | `sha512-KZASN9ZZMd/1KriSOZZvMQ2hAzJV4yG5fHZf6lxSZUAY3HZ4xeDNjubLKXYe6/H8AfucF5rCbcrjKnfd0/cgdg==` |
| `@privy-io/js-sdk-core` | 0.79.1 | 2026-10-21 | `sha512-wElB71FKVg8JkU6/eQngKrDSVHD0dOm9ZZzuNA7avBwqNdpUQiCSOqu0y4IEz6ThSrbjyKfaPTM/JdzVP6UCiQ==` |
| `@privy-io/routes` | 0.4.5 (dependency of js-sdk-core 0.79.1) | — | `sha512-eXdRJYHWrQI0zphLvwE87tUULRQFbi2QO2df80UkITK3phEGl4H0lpnuUU1Ug41y9ElyjMbp5gt07WqV0fw9Cg==` |
| `@privy-io/node` | 0.36.0 | 2026-10-16 | `sha512-ZgPQcjIwYSoLyHnQWRqSx27NbEMo6KUQepUVrm/yTpX9jI1BjBmHdUUXBsNS2cJZQ8f10mz/6jBmYZfIfXY2pA==` |
| `@privy-io/server-auth` | 1.32.5 (last publish 2026-04-01; not used below) | — | `sha512-e087vImrFHP4yAMx8alyCeCm6gk2JG/q7eSklFoST5mPTUV9TGKx7XNIyKOQQHxwKMpk5SBVIlkyJcqg3CuxSw==` |

The `privy-io` GitHub repositories are outside this session's repository scope and were not read.

## What our current proof binds (repository)

From `docs/qualification/privy-unfunded-proof/UNFUNDED_POLICY_PACKET.md` ("Identities") and
`scripts/privy_unfunded_proof/actual_packet.py`: app `cmuyj4smt00tw0dla2j19tlu7`, executor key quorum
`zu1qjdfqlbcq1ct7sdxendgg`, wallet and policy owner `a5gwmgrsn6903ac09lphyv9a`, server wallet
`bsb2feecuxl81dl5jz4u9xxo`, policy `c30racyru6duaipj815cvjce` with normalized rules SHA-256 `61860d20…0892b`,
chain `143`, route `POST https://api.privy.io/v1/wallets/{wallet_id}/rpc`, method `eth_signTransaction`. The policy
owns 4 of the 12 P21 controls (`chain`, `wallet_signer_binding`, `entrypoint_method`, `approvals`). The other 8 are
owned by the host, the Kuru contract or later stages ("Policy-owned and out-of-scope controls").

The repository does not record whether `c30r…` is attached to `bsb2…` as the wallet's `policy_ids` or as
`additional_signers[].override_policy_ids` of `zu1q…`. `docs/qualification/independent-enforcement/CAPABILITY_MATRIX.md`
row 2 names wallet `policy_ids`. Item 6 below depends on this.

---

## 1. Names and APIs for adding a signer; SDK version; development mode

**1a. Current React API: `useSigners().addSigners` and `removeSigners`. FACT (SDK source).**
`@privy-io/react-auth@3.51.0`, `dist/dts/index.d.ts` lines 4010–4039:

> `Hook to add signers to a user wallet.` … `addSigners: ({ address, signers, }: { address: string; signers: SignerInput; }) => Promise<{ user: User; }>;` … `Removes all signers from a wallet.` … `removeSigners: ({ address }: { address: string; }) => Promise<{ user: User; }>;` … `declare const useSigners: () => UseSignersInterface;`

`dist/dts/types-Bz_bVOEe.d.ts` lines 2833–2837:

> `type SessionSignerInput = { signerId: string; policyIds?: string[]; }[]; type SignerInput = SessionSignerInput;`

**1b. Older names are deprecated. FACT (SDK source).** Same `index.d.ts`, lines 3972–4007:

> `@deprecated in favor of useSigners` · `Hook to add session signers to a user wallet.` · `@deprecated in favor of addSigners` · `Headlessly grants access of the user wallet to a specified key quorum.`

`useDelegatedActions().delegateWallet` (lines 3941–3970) is the on-device ("delegated actions") flow. It is not the
TEE signer flow (see 4a).

**1c. What `addSigners` sends. FACT (SDK source).** `@privy-io/react-auth@3.51.0` `dist/esm/index-CaWn8tEz.mjs`
(minified) reads the wallet, appends the new signers and patches the wallet, signed with the user's own signer:

> `let e=[...(await f(t.privy,{wallet_id:o.id})).additional_signers,...De(n)];await a({wallet:o,additional_signers:e})` … `await A(t.privy,{wallet_id:a.id},r,{additional_signers:n})`

There, `f` = `getWallet`, `A` = `updateWallet` (import line: `getWallet as f,updateWallet as A` from
`@privy-io/js-sdk-core`), and `r` = `signWithUserSigner`. The mapping of the input is in `dist/esm/storage-Ufl800Ne.mjs`:

> `const b=e=>e?.map((e=>({signer_id:e.signerId,override_policy_ids:e.policyIds})))`

The route is `@privy-io/routes@0.4.5` `dist/esm`: `` Ct={path:`/api/v1/wallets/:wallet_id`,method:`PATCH`} ``
(exported as `WalletUpdate`). `@privy-io/js-sdk-core@0.79.1` signs it with the `privy-authorization-signature`
header (`dist/esm`, function `Yo`). The server REST shape is `@privy-io/node@0.36.0` `src/resources/wallets/wallets.ts`
lines 588–607:

> `A single additional signer for a wallet, with an optional policy override.` … `signer_id: SharedAPI.KeyQuorumID;` … `An optional list of up to one policy ID to enforce on the wallet.` `override_policy_ids?: PolicyInput;`

**1d. Signers can also be set when the wallet is created. FACT (SDK source).** `types-Bz_bVOEe.d.ts` lines 2791–2793:

> `Session signers to associate with the wallet at creation time.` `Only supported for TEE execution mode (\`user-controlled-server-wallets-only\`).` `signers?: SessionSignerInput;`

**1e. Signers are key quorums; the policy override is optional. FACT (docs, search index).**
https://docs.privy.io/wallets/using-wallets/signers/add-signers:

> "To provision server-side access for user's wallets, use the addSigners method from the useSigners hook" · `signerId`: "The key quorum ID that will be allowed to transact on the wallet." · "Each signer can only have one override policy at this time."

**1f. Minimum web SDK version. FACT (npm registry, measured here).** `useSigners` is not exported in `3.9.1`
(2025-12-18) and is exported in `3.10.0` (2025-12-23). Method: unpack each tarball and search
`dist/dts/index.d.ts` for `declare const useSigners`. The deprecated `useSessionSigners` first appears in `2.12.0`
(2025-04-28); `2.11.1` lacks it. The current release is `3.51.0`.

**1g. TEE execution is required. FACT (SDK source).** `dist/esm/index-CaWn8tEz.mjs`:

> `"Specifying signers in addSessionSigners is only supported for TEE execution and this app uses On-device execution. Pass an empty array for signers instead. Learn more https://docs.privy.io/recipes/tee-wallet-migration-guide"`

The app-level mode values are `'legacy-embedded-wallets-only' | 'user-controlled-server-wallets-only'`
(`types-Bz_bVOEe.d.ts` line 2327).

**1h. Development mode. UNKNOWN.** Privy separates environments by app, not by an SDK flag.
https://docs.privy.io/security/implementation-guide/security-checklist (search index): "Use different apps to
segregate development environments, userbases, API credentials, and more." INFERENCE: no path in
`addSessionSignersInternal` or `updateWallet` reads an environment flag. The only gate in that path is
`isUnifiedWallet` / `embeddedWallets.mode`. So whether a "development" app accepts signers depends on its TEE mode,
not on its being a development app. Login is a separate limit for development apps. The test-accounts page
(https://docs.privy.io/recipes/using-test-accounts, search index) states that non-test accounts in development apps
are limited to "5 requests every 5 minutes" for email OTP. Several judges logging in from one network could hit it.
*Smallest live check:* L1 below (dashboard read of app `cmuyj…` execution mode) and L3 (one test-account
`addSigners` with no policy-violating action).

## 2. A policy owned by a different owner; who edits it; removal and notice

**2a. The SDK does not restrict whose policy a signer may carry. FACT (SDK source), but the server rule is UNKNOWN.**
`override_policy_ids` is a bare `Array<string>` of policy IDs (`@privy-io/node@0.36.0`
`src/resources/wallets/wallets.ts` line 2489: `export type PolicyInput = Array<string>;`). Neither SDK checks the
policy's `owner_id` against the wallet owner. No document seen says the server requires the two to match.
*Smallest live check:* L4 below. A judge-test account adds our signer with `policyIds: ["c30racyru6duaipj815cvjce"]`,
then we read the wallet back (`GET /v1/wallets/{id}`) and confirm `additional_signers` holds
`{signer_id: zu1q…, override_policy_ids: [c30r…]}`.

**2b. The policy owner edits or deletes the policy. FACT.** `@privy-io/node@0.36.0`
`src/resources/policies/policies.ts` line 774: `owner_id: SharedAPI.KeyQuorumID | null;`. Update params (lines
1505–1525) carry `owner`/`owner_id` and the `'privy-authorization-signature'` header. Repository source evidence
(previously verified) records the doc rule. `docs/qualification/controlled-action-feasibility/CONTROLLED_ACTION_FEASIBILITY.md`
PV-OWN, https://docs.privy.io/controls/authorization-keys/owners/overview: "Policy owners update rules, change owner
and delete the policy. Wallet owners update wallet policies, signers and signer policies. Signers cannot update
owners, signers or policies and cannot export keys." `docs/qualification/route-restrictions/SOURCE_EVIDENCE.md` P8,
https://docs.privy.io/controls/policies/create-a-policy: "without a policy owner, the application secret alone can
update the policy." Our policy has owner `a5gw…` (builder only). So only the builder's owner key can change or
delete `c30r…`. The judge cannot change it, and our executor `zu1q…` cannot either.

**2c. A policy edit is shared by every wallet that uses it. INFERENCE.** A signer references the policy by ID
(2a). A builder edit of `c30r…` therefore applies at once to every judge wallet that carries it. A builder delete
leaves each signer pointing at a missing policy. The resulting behavior (deny or no policy) is UNKNOWN.
*Smallest live check:* none needed for stage B. Freeze `c30r…` during the demo. If a delete test is ever wanted,
run it on a throwaway policy and an unfunded test wallet only.

**2d. The judge (wallet owner) can remove the signer at any time and can also rewrite it. FACT (SDK source + docs).**
`removeSigners` sets the list to empty. `dist/esm/index-CaWn8tEz.mjs`:
`ne(i)?await a({wallet:i,additional_signers:[]}):await t.client.revokeDelegatedWallet()`.
https://docs.privy.io/wallets/using-wallets/signers/remove-signers (search index): "The removeSigners method will
remove all the signers, so only the user can transact on the wallet." · "After this action, your app will no longer
be able to take actions on behalf of the user". `removeSigners` removes **all** signers, not only ours. The same
`PATCH` (signed by the user, 1c) can also re-add our `signer_id` with a different or empty `override_policy_ids`.
https://docs.privy.io/recipes/wallets/user-and-server-signers (search index): "If you'd like the signer to have full
permission, pass an empty array ([])." The add-signers page (search index) says that without `policyIds` "no
policies will apply to the signers requests." INFERENCE: a judge's own client can widen what our key may sign on
their wallet. Our worker must therefore read the wallet's `additional_signers` before every signing request and
refuse unless our entry is exactly `override_policy_ids == ["c30racyru6duaipj815cvjce"]`. A gap between that read
and the sign request remains. In that gap the host-built request is still the only one sent (privy_signer.py refuses
non-exact requests), so widening cannot make our worker send a different transaction. It only removes the provider
backstop.

**2e. Learning about removal: poll, or a refused sign. No signer webhook was found. FACT (SDK source) + FACT (repo).**
`@privy-io/node@0.36.0` `src/resources/webhooks.ts` (4,770 lines) defines event `type` literals such as
`'wallet.archived'`, `'wallet.restored'`, `'wallet.private_key_export'`, `'user.wallet_created'` and
`'transaction.*'`. None names a signer or a wallet update. Docs search for a signer-change event
(https://docs.privy.io/api-reference/webhooks/overview) found none either. The wallet object exposes the list to
poll: `wallets.ts` line 4877 `additional_signers: WalletAdditionalSigner;`. Repository live evidence
`docs/qualification/p16/PROVIDER_SIGNING_RESULT_2026-10-08.md` (chain 10143, sign-only): after the owner removed
signer A, a wallet check returned `MATCH/NO_ADDITIONAL_SIGNER`, and "Removed A signer attempts A's configured call"
returned "`DENIED_UNCLASSIFIED`, HTTP 401, no code". INFERENCE: our server detects removal by `GET /v1/wallets/{id}`
before each action and treats an HTTP 401 on `/rpc` as "signer gone". `privy_signer.py` already maps a non-policy
error to `RpcError`, so a 401 is not counted as a policy denial.

## 3. Same rule types on a user wallet's signer as on a server wallet?

**3a. One policy object and one rule grammar for every wallet. FACT (SDK source).** `@privy-io/node@0.36.0`
`src/resources/policies/policies.ts` defines a single `Policy` (lines 749–782). It has no wallet-kind field: `id`,
`chain_type`, `created_at`, `name`, `owner_id`, `rules`, `version: '1.0'`. `PolicyMethod` (line 874) includes
`'eth_signTransaction'`. The condition `field_source` literals in that file include `'ethereum_transaction'`,
`'ethereum_calldata'`, `'ethereum_typed_data_domain'`, `'ethereum_typed_data_message'`,
`'ethereum_7702_authorization'`, `'system'` and `'reference'`. Signer overrides and wallet `policy_ids` both hold IDs of
this same resource (2a; `WalletUpdateParams.policy_ids`, line 7395).

**3b. A signer's override replaces the wallet's base policy for that signer's requests. FACT (SDK + docs).**
`@privy-io/node@0.36.0` `src/resources/users/users.ts` lines 1758–1762 (same text in `embedded-wallets.ts`
239–243):

> `The array of policy IDs that will be applied to wallet requests. If specified, this will override the base policy IDs set on the wallet. Currently, only one policy is supported per signer.`

https://docs.privy.io/recipes/wallets/conditional-signer-policies (search index): "When a signer submits a
transaction, Privy evaluates only that signer's override policy — not the policies of other signers." The search
index also attributes to https://docs.privy.io/controls/policies/stateful-policies a list of the policy sources that
can apply to a request: the wallet's assigned policy, owner policies, and signer override policies. The exact
precedence when a user wallet also has base `policy_ids` is therefore UNKNOWN. *Smallest live check:* L5 (one
denial-first row on a test user wallet that has no base policy).

**3c. Same enforcement on user wallets. INFERENCE.** Same policy resource (3a), same `/v1/wallets/{id}/rpc` route
(`@privy-io/routes@0.4.5`: `` xt={path:`/api/v1/wallets/:wallet_id/rpc`,method:`POST`} ``), and user TEE wallets
are the same wallet kind (`@privy-io/js-sdk-core@0.79.1` `dist/dts/index.d.ts` line 3380–3385: "Determines if a given
wallet account executes in the TEE." … "whether the wallet is a user-owned server wallet"). So chain, `to`, value,
`ethereum_calldata` (ABI) and method conditions should evaluate the same. This is not proven for user wallets.
*Smallest live check:* L5–L6.

**3d. Owner policies vs signer policies. FACT (repo docs) + INFERENCE.** Repository PV-OWN (2b): owners administer;
signers only sign within their override. INFERENCE: the judge's own signing (as owner) is not limited by our
override policy. Our policy limits only requests authorized by our key quorum. This is the intended split.

## 4. App settings and what the user sees

**4a. Dashboard settings. FACT (docs, search index), not checked against our dashboard.**
The search index attributes this text to the signers setup pages
(https://docs.privy.io/wallets/using-wallets/signers/configure-signers and
https://docs.privy.io/wallets/using-wallets/signers/setup; it did not attribute it to one of them):

> "Visit the Privy Dashboard and navigate to the User management > Authentication page for your app. Select the Advanced tab and toggle the Server-side access setting to enable signers for your app."
> "Navigate to the Wallet infrastructure > Authorization keys page and click on the Create new key button."

The SDK also requires TEE execution (1g). https://docs.privy.io/recipes/tee-wallet-migration-guide (search index):
"the updated interface allows a signer ID to be specified and for policies to be set which constrain that signer".
Our key quorum `zu1q…` and policy `c30r…` already exist in app `cmuyj…`. Whether that app's embedded wallets run in
TEE mode and whether "Server-side access" is on are UNKNOWN. *Smallest live check:* L1.

**4b. `addSigners` shows no Privy consent screen. FACT (SDK source) + FACT (docs).** In
`addSessionSignersInternal` (`dist/esm/index-CaWn8tEz.mjs`), the TEE branch calls `getWallet` and `updateWallet` and
opens no modal. In contrast, `delegateWallet` passes `showDelegationUIs:!0`. The type comment calls it "Headlessly
grants access" (1b). The user's authorization is the user-signer signature over the `PATCH`
(`signWithUserSigner`). The modal flows are the on-device ones: https://docs.privy.io/wallets/using-wallets/signers/revoke-wallets
(search index): "When invoked, the revokeWallets method will open a Privy modal where the user can either confirm the
revocation of their signer." **Our app must build its own consent screen.** The Privy developer terms
(https://www.privy.io/developer-terms-of-service, search index) state: "The developer must explain exactly how the
Delegated Action will function, including the signing rights of the developer or third parties." INFERENCE:
`signWithUserSigner` may raise an MFA prompt if the judge enrolled MFA. Not checked.

## 5. Rate limits, costs, plans

**5a. Plan limits. FACT (pricing page, search index), partial.** https://www.privy.io/pricing (search index): the free
Developer plan "includes 50K signatures and $1M transaction volume free every month". The index returned two
different MAU boundaries for the paid tiers (Core $299/month, Scale $499/month; up to 500 vs 499 MAU for Developer).
The exact boundary is UNKNOWN. INFERENCE: stage B for a judging panel is far below 50K signatures and the MAU caps.
Each judge who logs in counts as a monthly active user. *Smallest check:* read the plan page in our dashboard
(read-only, L1).

**5b. API rate limits. FACT (docs, search index), no wallet-specific number.**
https://docs.privy.io/api-reference/introduction (search index): "When you encounter a rate limit (HTTP 429
response), implement retry logic with exponential backoff". https://docs.privy.io/recipes/dashboard/optimizing
(search index) says limits apply per endpoint. No published per-second number for `/v1/wallets/{id}/rpc` or
`PATCH /v1/wallets/{id}` was found: UNKNOWN. INFERENCE: our worker sends one sign request per action, with no retry
(privy_signer.py). A 429 would surface as `RpcError`, not as a policy denial. Login OTP limits for development apps
are in 1h.

**5c. Signers have no separate charge in any source seen. UNKNOWN.** INFERENCE: each `eth_signTransaction` likely
counts as one signature toward 5a. *Smallest check:* dashboard usage page after L5.

## 6. What could stop the 19/19 proof from transferring to user wallets

The proof shows that Privy enforces policy `c30r…` for executor `zu1q…` on server wallet `bsb2…`. For a judge
wallet, each item below must hold. Each is INFERENCE unless marked.

1. **Different binding path.** If `c30r…` is on `bsb2…` as wallet `policy_ids`, the judge path (signer
   `override_policy_ids`) is a different enforcement path that the proof did not run. If it is already an override on
   `zu1q…`, the path is the same. Repo status: unrecorded (see "What our current proof binds"). Settle with L2.
2. **Cross-owner policy accepted?** UNKNOWN (2a). Settle with L4.
3. **App mode.** Signers need TEE mode and "Server-side access" (1g, 4a). An on-device app throws before any request.
   Settle with L1.
4. **Wallet-agnostic rules.** The proof is bound to wallet id and address `bsb2…`/`0x91BB…1b63`. The packet table
   shows conditions on chain, `to`, `value`, selector/function and approve spender, with no wallet-address condition.
   INFERENCE: the rules carry over unchanged. Not proven: the normalized rules live in
   `ROOT/.scratch/trade-prep-20261021/R3_TIGHTEN1_RESULT.json`, outside this checkout. The builder should confirm
   that no rule names `bsb2…` or `0x91BB…`.
5. **Judge can widen or remove the signer** (2d). The worker must re-read the signer entry before every action and
   refuse on any mismatch. A removal shows up as HTTP 401 (2e, P16).
6. **The base policy on the judge wallet.** The override should replace it (3b), but the precedence is not fully
   documented. Settle with L5 on a wallet with no base policy, which is the default for a new embedded wallet.
7. **Sign-only shape unchanged.** The route, method, `privy-authorization-signature` and request profile in
   `privy_signer.py` hold for any `wallet_id` matching `[A-Za-z0-9_-]{1,128}`. FACT (repo source, `_RPC_URL`). The
   proof's per-row request hashes and idempotency keys are bound to `bsb2…`, so a judge wallet needs a new packet
   identity. The 19/19 result cannot be reused as-is for another wallet.
8. **Executor separation.** `zu1q…` must not be the policy owner and must not belong to the judge wallet's owner
   quorum. FACT (SDK): `addSigners` adds only to `additional_signers`; the judge's wallet `owner_id` stays the user.
   The repo check that refuses an executor equal to the owner (`actual_packet.py` line 279) still applies.
9. **Funding and nonce are the judge's.** Nothing here touches funds. A judge wallet with no MON cannot pay gas.
   That is a stage-B flow concern, not a policy-transfer concern.

---

## Answer: does Privy accept our builder-owned policy when a user adds our signer?

Very probably yes, but it is not proven. Current SDKs (`@privy-io/react-auth` ≥ 3.10.0; read at 3.51.0) let the user
call `useSigners().addSigners({ address, signers: [{ signerId: "zu1qjdfqlbcq1ct7sdxendgg", policyIds: ["c30racyru6duaipj815cvjce"] }] })`.
This becomes a user-signed `PATCH /api/v1/wallets/{id}` that appends
`{ signer_id, override_policy_ids }`. The policy is referenced by ID. Neither SDK checks who owns it, and the docs
describe override policies as replacing the wallet's base policy for that signer's requests. Ownership stays where
we need it: only the builder's owner key can edit or delete `c30r…`, and the judge can only remove or rewrite their
own signer entry. Four things are not settled by any source available here. (a) Whether the Privy server accepts an
override policy owned by a different key quorum than the wallet owner. (b) Whether app `cmuyj…` runs in TEE mode
with "Server-side access" on. (c) Whether the user-wallet override path enforces the same 19 rows as the server-wallet
proof, if the proof used wallet `policy_ids`. (d) The precedence if a judge wallet also has a base policy. A judge
can widen or remove our signer at will and Privy sends no webhook for it, so the worker must read back its signer
entry before every sign request.

## Smallest live checks for builder approval (no funds, refusal first)

Each check uses only unfunded wallets and Privy test-account users. No transaction is broadcast; signed bytes are
discarded. Each is one bounded attempt with no retry, and the run stops on the first unexpected outcome.

| # | Check | Kind | What it settles |
| --- | --- | --- | --- |
| L1 | Dashboard read of app `cmuyj…`: embedded-wallet execution mode (TEE vs on-device), "Server-side access" toggle, plan page. Read only. | Read | 1g, 1h, 4a, 5a |
| L2 | `GET /v1/wallets/bsb2feecuxl81dl5jz4u9xxo`: record whether `c30r…` is in `policy_ids` or in `additional_signers[zu1q…].override_policy_ids`. | Read | item 6.1 |
| L3 | One test-account login creates an unfunded TEE embedded wallet. **Refusal first**: before any signer exists, our worker sends one in-policy row 1 request (`raw.allow_deposit_1_mon` shape) to that wallet's `/rpc` and expects a refusal (401/403). | Write (wallet create), sign refused | No standing access without a signer |
| L4 | Judge client calls `addSigners` with `signerId zu1q…`, `policyIds [c30r…]`. Then `GET` the wallet and confirm the exact `additional_signers` entry and that `owner_id` is not `zu1q…`. | Write (signer add) | 2a, item 6.2 |
| L5 | On that wallet, denial rows first: `raw.deny_plain_mon_transfer`, `raw.deny_deposit_wrong_chain`, `raw.deny_swap_with_mon`, each expecting `400 policy_violation`. Then one ALLOW (`raw.allow_deposit_1_mon`, sign only, bytes discarded). | Sign only | 3b, 3c, item 6.6 |
| L6 | Optional: full 19-row packet under a new packet identity bound to the test wallet id. | Sign only | full transfer of 19/19 |
| L7 | Judge client calls `removeSigners`. `GET` shows no `zu1q…` entry. One worker sign request expects a refusal (HTTP 401, as in P16). | Write (signer remove), sign refused | 2d, 2e |
