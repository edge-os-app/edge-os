# Privy wallet creation and confirmed binding

Status: LOCAL implementation candidate for PRIVY-WALLET-CONNECTION-L3-20261016. It creates no actual wallet,
delegation, signer, policy, funding, signature or broadcast. No actual Privy account call qualified it.

## Flow

1. `prepare` saves the setup identity (unchanged).
2. `POST /v1/wallet-setup/agents/{agent}/browser-begin` locks the setup row and, only for `REQUESTED` with no
   dispatch and no cancellation, commits `DISPATCH_INTENT` (state `PENDING`) and answers `create_permitted: true`.
   Every other begin (duplicate, second tab, retry after a lost reply, cancelled, confirmed, unknown) answers
   `false` and changes nothing.
3. Only after `create_permitted: true`, the browser calls pinned `@privy-io/react-auth` 3.47.0
   `useCreateWallet().createWallet({ createAdditional: true })`. The installed declaration returns
   `Wallet { id?: string | null; address; chainType; walletIndex: number | null }`.
4. The browser keeps the exact returned wallet in `localStorage` (`edge-os:wallet-claim:<agent>`) before it calls
   `complete`. A refresh or API restart resumes from that claim; it never begins or creates again.
5. `POST .../complete {wallet_id, address}` retains the untrusted claim (`RESULT_RETURNED`, `claimed_address`) and
   then asks the owner-bound lookup. It binds only when the lookup matches the same ID and address.
6. A returned wallet without `id` is sent as an address-only claim; the server resolves the ID itself (below).
   A non-Ethereum result, a lookup failure or any mismatch stays `PENDING`/`UNKNOWN`.
7. `resume` with the owner-bound lookup re-runs completion from the claim the server retained (`claimed_address`,
   `claimed_wallet_index`, any returned ID), so an API restart or another browser needs no local storage. Without
   a retained claim it uses the existing reconciliation, which never creates. The browser keeps its own copy under
   `edge-os:wallet-claim:<verified user id>:<agent>`, so another signed-in owner never reads it.

## Independent lookup and isolation

- `wallet_setup/lookup_client.py` (`OwnerBoundLookupProvider`) is built per request by the router's
  `get_provider` from the verified `Principal` (`privy_did`, `user_id`) when `EDGE_OS_WALLET_LOOKUP_SOCKET` is set.
  It never creates; `create_wallet` raises `WalletProviderUnavailable`.
- `scripts/privy_wallet_lookup/lookup_server.py` is the separate trusted process. It alone reads `PRIVY_APP_ID` and
  `PRIVY_APP_SECRET` at explicit startup. Its one operation is `lookup_embedded_wallet`: fixed
  `GET https://api.privy.io/v1/users/{did}`, default certificate validation, no redirect, no retry, 10 s deadline,
  256 KiB response cap. The socket directory must be owned by the user with mode 0700; the socket is 0600; peers
  must run as the same user. Frames: 4-byte length + JSON object, at most 4096 bytes.
- `wallet_setup/lookup_matching.py` matches exactly one linked account with `type=wallet`,
  `wallet_client_type=privy`, `chain_type=ethereum`, the claimed address and the claimed ID, in the user record
  whose `id` equals the verified DID. A wallet `owner_id` (key quorum) and `entity` (attribution) are never read.
- When that matched link has no ID, and only then, the process calls the fixed read-only
  `POST https://api.privy.io/v1/wallets/address` with exactly `{"address": <claimed address>}`. The answer must carry
  the same address, `chain_type` `ethereum` and a valid `id`; every available ID (link, answer, browser claim) must
  agree. Context7 (2026-10-16) also lists a `GET /api/wallets/address/{address}` form; this code follows the
  controller-verified official POST page.
- An existing socket target is refused at startup, never unlinked.

## Configuration

`EDGE_OS_WALLET_LOOKUP_SOCKET` is a short absolute path, valid only with `wallet_provider=unavailable`. Unset keeps
the fixture and unavailable behavior. `provider_info` answers `privy_lookup` for the owner-bound lookup.

## Known limits (for later actual qualification)

- REST field names come from current docs, not a pinned runtime sample; an unsupported shape stays UNKNOWN.
- The macOS same-user peer check (`LOCAL_PEERCRED`) and all live socket behavior are untested until the IPC slot.
- A begin permitted while the browser has no verified user id makes no SDK call and leaves the setup PENDING.
