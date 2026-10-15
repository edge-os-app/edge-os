# Privy sign-only HTTP adapter

Task `PRIVY-SIGNER-HTTP-L3-20261014-LOCAL-v1`, #58 Stage 3, P20/P21 preparation. Base `012fb1597d061e4d263afc3d8be0538c4298b48f`. Sources checked 2026-10-14.

Stage: LOCAL. The adapter is unmounted and disabled by default. No caller, setting, factory or composition constructs it. No Privy request, credential, wallet, policy, signature or broadcast was used to build or test it.

## Responsibility

`edge_os_api.execution.privy_signer.PrivySignerClient` satisfies the existing `SignerClient` seam in `execution/original_transaction.py`:

```python
rpc(wallet_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]
```

It sends one `eth_signTransaction` request for one original transaction to `POST https://api.privy.io/v1/wallets/{wallet_id}/rpc` through an injected `HttpTransport`. It returns the existing signed envelope, a local unsent refusal, or raises `RpcError`/`ReplyLost`, which the caller records as `SIGNING_UNKNOWN`. It does not validate signed bytes; the caller's `validate_signed` does that independently.

The adapter itself holds no key. The authorization signature comes from an injected callable. `make_p256_authorizer` (below, task `PRIVY-REQUEST-AUTHORIZATION-L3-20261015-LOCAL-v1`) builds that callable from an already loaded P-256 key object. Neither task writes a general canonicalizer, key loader or signing service.

## Construction

Keyword-only, all injected, no environment, file or network access:

| Input | Meaning |
|---|---|
| `app_id`, `app_secret` | Privy app credentials for Basic authentication and `privy-app-id`. Validated as non-empty printable ASCII. Never in `repr`, messages or causes. |
| `authorize` | `Callable[[Mapping], str]`. Receives the authorization payload and returns the `privy-authorization-signature` value. |
| `request_id` | The original request identity (the caller's `attempt_id`). Sent as `privy-idempotency-key`. Never renewed. |
| `request_expiry_ms` | Absolute Unix milliseconds. Sent as `privy-request-expiry`. Limits when Privy processes the request. It is not an onchain lifetime for signed bytes. |
| `http` | The existing `HttpTransport` seam. Production would pass `StdlibHttpTransport`. |
| `connect_timeout_seconds`, `deadline_monotonic`, `max_response_bytes` | Finite transport bounds. |
| `cancel` | Optional cancellation flag. |
| `wall_clock_ms`, `monotonic` | Clocks, injectable for tests. |

One adapter serves one original request. The mounting task must construct one adapter per attempt with `request_id == prepared.attempt_id` and test that tie; this seam (`rpc(wallet_id, body)`) cannot check it. A second `rpc` call on the same adapter raises `RpcError` and sends nothing: the first call may have produced a signature, so the second call cannot be a definite refusal.

## Accepted request

Exactly the body `OriginalTransactionTransport._candidate` builds, unchanged:

```json
{"method": "eth_signTransaction",
 "params": {"transaction": {"type": 2, "chain_id": …, "nonce": …, "to": "0x…", "value": …, "data": "0x…",
                            "gas_limit": …, "max_fee_per_gas": …, "max_priority_fee_per_gas": …}}}
```

- `type` is the integer 2. Types 0, 1 and 4 are refused.
- The six quantities are JSON integers in `0 … 2^53−1` (`chain_id` at least 1). Booleans, floats, strings and larger integers are refused. RFC 8785 writes numbers as IEEE doubles, so a larger integer would make the signed payload differ from the sent body. The adapter never converts, rounds, fills or rewrites a value.
- `to` is a 20-byte hex address. `data` is even-length hex.
- Any other key at any level is refused, including `from`, `gas_price`, `authorization_list` (EIP-7702 delegation), `caip2` and `chain_type`.
- `wallet_id` is 1–128 characters of `[A-Za-z0-9_-]`. Anything else, including `/`, `..`, `?`, `#`, `%` or whitespace, is refused.
- The encoded body is at most 65 536 bytes.

Supported domain: the existing ERC-20 route sends `value` 0 and carries raw token amounts inside the hex calldata, so the integer limit does not restrict token amounts. Native MON legs are already unsupported by the caller. A gas limit or fee above `2^53−1` is unsupported.

## Request

One HTTP request, no retry, redirect, fallback, renewal or second authorization:

- URL `https://api.privy.io/v1/wallets/{wallet_id}/rpc`, no trailing slash.
- Body: compact JSON with sorted keys, ASCII only.
- Headers: `authorization: Basic base64(app_id:app_secret)`, `content-type: application/json`, `privy-app-id`, `privy-authorization-signature`, `privy-idempotency-key`, `privy-request-expiry`.
- Authorization payload given to `authorize`:
  `{"version": 1, "method": "POST", "url": <url>, "body": <body>, "headers": {"privy-app-id", "privy-idempotency-key", "privy-request-expiry"}}`.

Sorted compact JSON is not a general RFC 8785 implementation. Within the accepted domain (ASCII strings, safe integers, no floats) the two produce the same bytes; this is an inference from RFC 8785, not a tested claim about Privy's verifier. The adapter gives `authorize` its own copy. If the callback changes that copy, the adapter refuses before sending.

## Request authorizer

Task `PRIVY-REQUEST-AUTHORIZATION-L3-20261015-LOCAL-v1`, #58 Stage 3, P21/P26 connection dependency. Base `febfeb47b8ee5ec3907512036712eb36f5767444`. Sources checked 2026-10-15. Stage: LOCAL and unmounted.

```python
make_p256_authorizer(*, private_key: ec.EllipticCurvePrivateKey) -> Callable[[Mapping[str, Any]], str]
```

- `private_key` is a `cryptography` private-key object on `SECP256R1` (NIST P-256). Public keys, other curves (P-384, secp256k1), Ed25519, bytes, strings and other objects raise `TypeError` at construction. The message contains no input value. Construction signs nothing.
- The caller owns key acquisition and custody. This module adds no PEM/DER loader, `wallet-auth:` parser, environment variable, file lookup, cache or key generation.
- The returned callable reads the payload without changing it and accepts only the exact profile `PrivySignerClient.rpc` builds:
  1. Top-level keys exactly `version`, `method`, `url`, `body`, `headers`.
  2. `version` is the integer 1 (not a boolean or float). `method` is `POST`.
  3. `url` is exactly `https://api.privy.io/v1/wallets/{wallet_id}/rpc` with a valid wallet ID. Other origins, schemes, paths, queries, fragments, percent-encoding, trailing slashes and line breaks are refused.
  4. `body` passes the adapter's existing request rules for that wallet, including the 65 536-byte limit. The authorizer reuses those rules; it accepts no new request domain.
  5. `headers` are exactly `privy-app-id`, `privy-idempotency-key` and `privy-request-expiry`. This profile requires all three because the adapter always sends them. The app ID and request ID pass the adapter's rules. The expiry is a canonical positive ASCII decimal string: no leading zero, sign, space, exponent, non-ASCII digit or JSON number. No clock is read and no expiry is renewed.
- Anything else raises `ValueError` before signing, with one stable message, no cause or context and no payload value. Inside `PrivySignerClient`, any authorizer exception becomes `LOCAL_UNSENT/AUTHORIZATION_FAILED` before HTTP and its text is discarded. An interrupt (`KeyboardInterrupt`) propagates with nothing sent.
- Accepted payloads are serialized with the adapter's own compact sorted-key ASCII JSON, encoded as UTF-8 (identical to ASCII here), and signed with `private_key.sign(message, ec.ECDSA(hashes.SHA256()))`. The returned header is `base64.b64encode(der_signature)`: standard Base64 with padding, of the ASN.1 DER ECDSA signature. Not Base64url, JWS, raw `r || s`, Keccak, secp256k1 or an extra digest.

### Why this restricted encoding equals RFC 8785 here

This is a narrow serializer for one accepted profile, not a JSON canonicalizer. The code carries a `shortcut:` comment that requires a reviewed RFC 8785 implementation before the profile widens.

- Every key is a fixed ASCII field name, so Python's sort order equals RFC 8785's UTF-16 code-unit order (RFC 8785 §3.2.3).
- Every string value passes an ASCII identifier, URL, address, calldata, method or decimal-string rule. No escape other than `\"`/`\\` can occur and none of those characters is accepted, so string serialization matches §3.2.2.2.
- Every number is the integer 1, 2 or a quantity in `0 … 2^53−1`. For these, Python's decimal text equals the ECMAScript number serialization required by §3.2.2.3. Booleans, floats, NaN, infinities and larger integers are refused.
- Compact separators emit no whitespace (§3.2.1). ASCII bytes are UTF-8 bytes (§3.2.4).

This equivalence is an inference from RFC 8785 sections 3.1–3.2.4. It is tested against one independently authored literal and its boundary variant, not against a general RFC 8785 implementation or Privy.

### Evidence

- The fixture `canonical_authorization_payload` in `apps/api/tests/fixtures/privy_signer/expected_request.json` is a hand-written literal. No test derives it from the module's encoder.
- Synthetic P-256 keys are generated in memory inside each test and never saved. Tests decode the header as strict standard Base64, parse it as DER `(r, s)`, and verify it with the matching public key over the literal's UTF-8 bytes with ECDSA SHA-256. They do not compare signature bytes, because ECDSA signatures differ between runs.
- Covered: the literal; reordered dictionary insertion; zero and `9007199254740991` quantities against a second literal; a wrong verification key; each signed field altered independently (`InvalidSignature`); refused key types and curves; refused payload shapes, signed-header sets, URLs, header values, numeric and Unicode escapes, non-JSON values, circular and non-dict mappings, with zero `sign` calls and an unchanged payload.
- Through the real caller: one authorization and one HTTP call, with the signature verified over a payload rebuilt by hand from the recorded URL, headers and body; one broadcast with the original transaction hash; nonce and sender tampering still rejected with zero broadcasts; a failing key gives `SIGNER_REFUSED` with zero HTTP; stops before authorization reach no key; stops during signing send nothing and keep the original expiry; a lost or rejected reply stays `SIGNING_UNKNOWN` and a second use signs and sends nothing; a reply that echoes the generated signature stays UNKNOWN and no exception or log repeats the signature or the private scalar.
- The P-256 key signs the Privy request only. The wallet transaction signature in these tests is the authored recording. No claim about memory zeroization follows.

### Limits

Local PASS proves synthetic cryptographic compatibility for one restricted payload profile and the existing caller over doubles. It does not prove that Privy accepts a signature, actual key custody, resource ownership, real login, wallet creation or lookup, application mounting, policy enforcement or an onchain transaction. The P21 opaque-program restriction stays `UNKNOWN` ([policy binding feasibility](../route-restrictions/PRIVY_POLICY_BINDING_FEASIBILITY.md)). No new spending, budget, funds or asset selection follows.

## Prepared future operation: real login for two owners

Status: PREPARED ONLY. Not executed. It needs its own builder authorization naming exact destinations and bounds. The expected result is real email login through the existing browser and API verifier, two distinct durable owners, and observed absence of wallet creation. It does not qualify trading.

### Inputs required before activation

Freeze the exact approved application commit, browser origin, API origin, owned local database and resource handles, the Privy development app identity and allowed origins, two builder-controlled email owners and the operation window. Use private references for the owners, not email addresses, in shared packets. Missing inputs prevent activation, not local implementation.

Use `EDGE_OS_ENV=local`. Set `NEXT_PUBLIC_PRIVY_APP_ID` and `EDGE_OS_PRIVY_APP_ID` to the same app. Set `NEXT_PUBLIC_API_BASE_URL` and an exact CORS allow-list for the frozen origins. Keep the injected test-auth object absent; the application must show the real Privy path with no fixture-auth label.

| Material | Permitted source and role |
|---|---|
| Login verification key | Public key from the selected app's Dashboard, supplied privately to `EDGE_OS_PRIVY_VERIFICATION_KEY`. Record only source path, public-key fingerprint, key type/curve and app identity. Startup must accept EC P-256. No JWKS lookup is adopted. |
| Owner access tokens | Issued by the app's real email login through the existing `getAccessToken`. Keep tokens, refresh tokens and OTP codes out of logs, HAR exports, model inputs and reports. |
| Request authorization key | Only synthetic keys are used in this LOCAL unit. Real resource ownership, additional-signer authority, acquisition, storage and owner/executor separation need a later packet. The login public key cannot authorize wallet RPC requests. |
| Wallet transaction key | Stays with Privy. Never acquired. Login QA needs no wallet private key, app secret, authorization private key or key export. |

The official access-token page describes ES256 tokens but names the verification key Ed25519. Check the actual Dashboard key with the existing parser and verify a real token through the existing verifier. Stop on a mismatch. Do not weaken the parser, change algorithms or invent a JWKS endpoint.

### Procedure after separate authorization

1. Confirm the exact code, configuration names, local resource ownership, two private owner references and the operation authorization. Confirm both chain configs keep `createOnLogin: "off"`.
2. Inspect the app's automatic-wallet settings with the authorized Dashboard read. Do not change them. If they could create a wallet, stop before login and report the conflict.
3. Record each owner's embedded-wallet before-state with the authorized read route. Prefer owners with none. Keep metadata private; record counts and observation identities only.
4. Open two isolated browser contexts. The builder enters each email and OTP directly. No agent transcript collects them.
5. For each owner, use the unchanged real browser bridge and call `GET /v1/me`. Record success, a hashed owner reference and the returned UUID. Repeated requests keep one UUID per owner; A and B differ.
6. In the owned verifier process, record token metadata without saving the token: ES256, issuer, audience match, hashed subject, subject length, session-claim type/length, `exp - iat`, and whether the two identity-data claims are present. Do not infer token class from `sid` alone.
7. Restart the owned API with the same database and public key. The refreshed browser session maps to the same owner UUID.
8. For an already authorized inert record owned by A, request it with B's token and compare the 404 envelope with a missing ID. If no such record exists, record `NOT_RUN`. Do not create a research request that could call a model.
9. Sign out A; A's client state clears and B's session stays B. Sign A in again and confirm its UUID. Do not assert immediate backend revocation of A's old token.
10. Read the same wallet metadata after each login. Both owners keep their before-state wallet counts with zero new embedded wallets. A configuration test or an application-database count alone does not prove this.
11. Save a redacted result: build, origins, key provenance/fingerprint, owner hashes, claim metadata, response statuses, wallet observations, restart evidence and limits. Stop and clean up only owned local processes and resources.

The login packet may authorize provider login requests, `/v1/me`, owner-scoped saved-record reads and named Dashboard metadata reads. It authorizes no wallet creation, signer attachment, policy change, wallet RPC signature, quote, broadcast, funding, key export, Dashboard rotation or identity-token enablement. P01 rotation (R2) and identity-token (R4) checks stay outside it unless separately authorized.

## Outcomes

| Situation | Provider effect | Result | Caller records |
|---|---|---|---|
| Invalid wallet ID or body on the first call | None: no authorization, no HTTP | `{"error": {"code": "LOCAL_UNSENT", "reason": <stable code>}}` | `DEFINITELY_UNSENT` / `SIGNER_REFUSED` |
| A body that cannot be read, copied or encoded (for example a non-dict mapping) | None: no authorization, no HTTP | `LOCAL_UNSENT` (`BODY_INVALID`) | `SIGNER_REFUSED` |
| Cancelled, deadline passed or request expiry passed before authorization, or a stop check that raises or returns an unusable value | None | `LOCAL_UNSENT` | `SIGNER_REFUSED` |
| `authorize` raises, returns an invalid value or changes the payload, including a type-only change such as `0` → `false` or `7` → `7.0`, or makes it unencodable | None: no HTTP; one local authorization happened | `LOCAL_UNSENT` | `SIGNER_REFUSED` |
| Cancelled, deadline or expiry passed, or a stop check failed, after authorization and before HTTP | None: no HTTP; one local authorization happened | `LOCAL_UNSENT` | `SIGNER_REFUSED` |
| Second `rpc` call on one adapter | Unknown (first call) | `RpcError` | `SIGNING_UNKNOWN` |
| Timeout, cancellation during the request, any transport exception | Unknown | `ReplyLost` | `SIGNING_UNKNOWN` |
| Disconnect or truncated reply: the shipped transport reports malformed framing (`HttpProviderError`) or a socket timeout | Unknown | `RpcError` or `ReplyLost` (equivalent: both are `SIGNING_UNKNOWN`) | `SIGNING_UNKNOWN` |
| Any status other than 200, including every documented Privy error code and redirects | Unknown | `RpcError` | `SIGNING_UNKNOWN` |
| Oversized, non-identity encoding, non-UTF-8, non-JSON, non-object, too deeply nested, HTML | Unknown | `RpcError` | `SIGNING_UNKNOWN` |
| 200 reply with `error`, wrong `method`, a repeated key at any depth (even with identical values), extra or missing fields, non-hex or oversized bytes, encoding other than `rlp` | Unknown | `RpcError` | `SIGNING_UNKNOWN` |
| Reply that echoes the app secret, the Basic token or the authorization signature | Unknown | `RpcError` | `SIGNING_UNKNOWN` |
| 200 `{"method": "eth_signTransaction", "data": {"signed_transaction": "0x…", "encoding": "rlp"}}` | Signed | `{"data": {"signed_transaction", "encoding"}}` | `validate_signed` decides |

`LOCAL_UNSENT` is the only shape `is_signer_refusal` treats as a refusal, and the adapter returns it only when it made no HTTP call. The caller's `SIGNER_REFUSED` is a coarse client code. It is not proof of a Privy policy denial or any P21 enforcement.

No Privy reply becomes a definite refusal. Privy documents error codes (`policy_violation`, `request_expired`, the authorization-signature codes and others) but not the JSON shape of an error body. The adapter therefore cannot recognize a documented refusal, so every error stays UNKNOWN.

The payload-change check compares encoded JSON, not Python equality, because `0 == False` and `7 == 7.0` in Python but sign different bytes. An interrupt (`KeyboardInterrupt`, `SystemExit`) is never turned into a refusal: before send it propagates with nothing sent; during the request it propagates and the caller's attempt stays in flight and UNKNOWN.

Errors carry a stable code only. They are raised outside exception handlers, so no `__cause__` or `__context__` holds provider text, credentials, the signature or signed bytes.

## Recovery

Privy documents that it stores the request and its response for 24 hours per idempotency key and returns the stored response for a repeated key with a matching body, without re-executing; for `/rpc` this covers 4xx and 5xx replies too, and a policy violation deletes the record ([idempotency keys](https://docs.privy.io/api-reference/idempotency-keys)). That replay is documented but untested here, and this adapter and its caller never make a second call. After `SIGNING_UNKNOWN` the caller makes no second signer call and no broadcast; only receipt reconciliation settles the original liability. This adapter does not change that rule.

## Evidence and limits

- Behaviour tests: `apps/api/tests/execution/test_privy_signer.py`, with injected HTTP and authorization doubles and literal expected request bytes and headers. They run the real caller `OriginalTransactionTransport` for the positive path, tampered replies and a lost reply.
- The tests prove request shaping, refusal, bounds and redaction inside this process. They do not prove Privy's acceptance, the authorization signer's cryptography, RFC 8785 equality, policy enforcement or independent P21 enforcement.
- Pure checks run with the qualified dependencies read-only (`-k "not loopback"`).
- The `test_loopback_*` tests drive the shipped `StdlibHttpTransport` against an owned `127.0.0.1` listener through its injected connector, keeping the literal Privy URL. They prove local socket and HTTP handling only, not public DNS, TLS or Privy acceptance. The worker ran them, the affected execution suite and sentinel scans on an earlier candidate (`5c49c96`); every changed candidate needs its own complete run under a separate grant.
- Not done here: actual wallet creation or attachment, policy administration, broadcast, real Privy authentication, executor host or key custody, and application mounting.
- Sources: [eth_signTransaction](https://docs.privy.io/api-reference/wallets/ethereum/eth-sign-transaction), [direct request signing](https://docs.privy.io/controls/authorization-keys/using-owners/sign/direct-implementation), [request expiry](https://docs.privy.io/api-reference/request-expiry), [idempotency keys](https://docs.privy.io/api-reference/idempotency-keys), [API error codes](https://docs.privy.io/basics/troubleshooting/error-handling/api-errors).
- Authorizer sources, checked 2026-10-15 (Context7 `/llmstxt/privy_io_llms-full_txt` and `/pyca/cryptography`): [signature payload and direct signing](https://docs.privy.io/controls/authorization-keys/using-owners/sign/direct-implementation) (payload fields, RFC 8785, P-256, Base64 header; the official Go example signs SHA-256 and returns Base64 DER), [RFC 8785 sections 3.1–3.2.4](https://www.rfc-editor.org/rfc/rfc8785), and [cryptography ECDSA](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ec/) (`sign` returns DER; `verify` raises `InvalidSignature`).
