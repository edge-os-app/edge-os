# Actual original-transaction qualification packet (PROPOSED)

Status: **PROPOSED; every actual step is NOT_RUN.** Prepared 2026-10-12 for #58 after the ORIGINAL-LOCAL milestone (`RELEASE-E2E-L2-20261012-ORIGINAL-LOCAL-v1`). This packet authorizes nothing. It lists what one bounded actual qualification must fix and prove before any funded action. The local milestone proves application wiring over AUTHORED recorded responses only.

## What the local milestone proves (and does not)

| Proven locally (AUTHORED recordings, no egress) | Not proven |
|---|---|
| One original envelope per admitted action, saved before signing; signed bytes and the Keccak-256 hash of the full signed serialization saved before one broadcast | Any Privy, Kuru, Monad RPC or QuickNode behavior |
| EIP-1559-only decoding, field-by-field and sender validation; no retry, re-quote, re-nonce, re-fee, re-sign or second action | Deployed entrypoint/router bytecode identity; the actual quote schema; the real selector |
| Receipt binding through P20 `normalize_observation` with the saved candidate, chain, wallet and hash; missing actuals keep the P22 liability | Real receipts, Transfer-log layouts, fee-on-transfer or rebasing tokens |
| Holdings observations with wallet, chain, block, time and finality; stale, partial or wrong-decimal readings refused | Real balance reads, finality depth, reorg behavior |
| One published test signer address in a fixture wallet | Separate actual user wallets (PU06), delegated signer, policy enforcement |

## Unresolved values the builder must fix (each blocks an actual run)

1. **Network and route.** Chain (`143` documented for Flow; testnet Flow unknown), entrypoint and router addresses, method, exact ABI and real selector (K1–K3, S1–S2 pins in `docs/qualification/kuru-flow-adapter/SOURCE_FIXTURE_MANIFEST.md`).
2. **Wallet, signer and policy administration.** The user-owned wallet, the restricted agent signer, a policy-resource owner outside executor control (`POLICY_ADMIN_OWNER_MISSING` today), and the opaque-`program` control (row 12 of `CONTROL_RESTRICTIONS.md`, `UNKNOWN`). P21 unknown controls remain barriers.
3. **Bounds.** Request, attempt and deadline per action; signing and broadcast timeouts; response byte limits; gas limit and fee caps (today the authored `gas_limit × max_fee_per_gas` must fit the reserved per-action gas); action count; raw input, minimum output and slippage; intent and mandate expiry; stop and removal behavior; total cost ceiling.
4. **Idempotency and resend.** The exact Privy idempotency semantics for `POST /v1/wallets/{wallet_id}/rpc`, and whether a byte-identical resend of saved signed bytes is ever allowed. Resend is disabled until this is decided.
5. **Receipt and holdings sources.** The independent RPC provider for receipts and balances, its finality tag, and how token decimals and Transfer logs are read for the selected assets.

## Proof the actual run must produce

- **Positive:** one action; decision, revision, consent, reservations, envelope, signing request, signed-byte hash, broadcast reply, receipt, decoded actual input/output/gas and residual holdings, each saved and reopened.
- **Negative:** a deterministic local admission denial; an independent provider (policy) denial not masked by a local counter; a wrong-signer or wrong-field signed response refused before broadcast.
- **Interruption:** a lost signer reply and a lost broadcast reply each reconcile the original action only; no second economic action; unknown capacity retained until a bound receipt settles it.
- **Removal:** owner removal plus an independent post-removal denial.

## Boundaries

No credential, account, wallet or policy change, signing, broadcast, spending, hosting or publication is authorized by this document. A real run needs one exact released packet with the values above and recorded builder approval.
