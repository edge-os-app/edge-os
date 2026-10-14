# Privy sign-only HTTP adapter

Task `PRIVY-SIGNER-HTTP-L3-20261014-LOCAL-v1`, #58 Stage 3, P20/P21 preparation. Base `012fb1597d061e4d263afc3d8be0538c4298b48f`. Sources checked 2026-10-14.

Stage: LOCAL. The adapter is unmounted and disabled by default. No caller, setting, factory or composition constructs it. No Privy request, credential, wallet, policy, signature or broadcast was used to build or test it.

## Responsibility

`edge_os_api.execution.privy_signer.PrivySignerClient` satisfies the existing `SignerClient` seam in `execution/original_transaction.py`:

```python
rpc(wallet_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]
```

It sends one `eth_signTransaction` request for one original transaction to `POST https://api.privy.io/v1/wallets/{wallet_id}/rpc` through an injected `HttpTransport`. It returns the existing signed envelope, a local unsent refusal, or raises `RpcError`/`ReplyLost`, which the caller records as `SIGNING_UNKNOWN`. It does not validate signed bytes; the caller's `validate_signed` does that independently.

It holds no key and signs nothing. The authorization signature comes from an injected callable. That callable is a required, still-unimplemented integration dependency: a P-256 key holder that canonicalizes the payload per RFC 8785. This task writes no canonicalizer, key loader or signing service.

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

Sorted compact JSON is not a general RFC 8785 implementation. Within the accepted domain (ASCII strings, safe integers, no floats) the two produce the same bytes; this is an inference from RFC 8785, not a tested claim about the external signer. The adapter gives `authorize` its own copy. If the callback changes that copy, the adapter refuses before sending.

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
