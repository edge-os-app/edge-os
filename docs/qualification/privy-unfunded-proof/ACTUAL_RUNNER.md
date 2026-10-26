# Local unfunded actual proof runner

Task `ACTUAL-POLICY-PROOF-L3-20261018`, extended by `UNFUNDED-POLICY-PROOF-L3-20261022`, `POLICY-PROOF-V2-L3-20261022` and `POLICY-PROOF-V3-L3-20261022`. Status `LOCAL`. Provider proof `UNQUALIFIED`. Every result is `LOCAL_TESTED`.

This document describes the successor of the accepted synthetic driver. Exactly one policy-layer packet and one raw profile are registered. It does not approve any trade, funding, route, policy change or provider request. The live proof is run only by the controller as operator.

## Files

| Path | Responsibility |
| --- | --- |
| `scripts/privy_unfunded_proof/actual_packet.py` | The frozen exact actual packet, the twelve P21 controls, the position-inventory obligation, the type-4 authority gate and the code-owned approval registry. |
| `scripts/privy_unfunded_proof/actual_profile.py` | The qualified reply/decoder profile and its code-owned registry. |
| `scripts/privy_unfunded_proof/actual_transport.py` | One-shot bounded sign-only transport to the exact approved destination, with a separate connect bound and per-request deadline bound. |
| `scripts/privy_unfunded_proof/actual_runner.py` | `run_actual_specimen`: admission, one-use intent, bounded capture, classification and stop. |
| `scripts/privy_unfunded_proof/actual_run.py` | The operator command: dry run, unfunded confirmation, one ordered live run, stop on mismatch. |
| `tests/privy_unfunded_proof/test_actual_proof_runner.py` | Offline regression evidence. |
| `tests/privy_unfunded_proof/test_unfunded_policy_packet.py` | Offline evidence for the frozen policy-layer packet, profile and command. |
| `tests/privy_unfunded_proof/_actual_support.py` | SYNTHETIC doubles used only by these tests. |
| `docs/qualification/privy-unfunded-proof/UNFUNDED_POLICY_PACKET.md` | The frozen packet, exact bodies, ordered requests and expected-outcome table. |
| `docs/qualification/privy-unfunded-proof/ACTUAL_PROOF_OPERATION_INPUTS.json` | The exact frozen operation inputs. |

## Default refusal

The code-owned registries hold two sealed packets (the v3 policy-layer packet and the control-proof packet of `docs/qualification/inapp-trade/CONTROL_PROOFS_PLAN.md`), one raw profile and their two actual table manifests. Every other packet, profile or table refuses before any credential read, socket or file effect. An unknown packet refuses with `ACTUAL_PACKET_NOT_APPROVED`.

A caller cannot approve a packet with a Boolean, function argument, flag or environment setting. `run_actual_specimen` takes no approval, profile or authority mapping. Resolution reads only `CODE_OWNED_PACKET_APPROVALS`, `QUALIFIED_ACTUAL_PROFILES`, `CODE_OWNED_TYPE4_AUTHORITIES` and `CODE_OWNED_ACTUAL_MANIFESTS`. The same rule applies to every entry.

The synthetic driver keeps its boundary. `run_specimen` still accepts only `SYNTHETIC_FIXTURE`, and `ACTUAL_RUN_REFUSED` is unchanged.

## Admission order

1. Resolve the code-owned packet.
2. Bind the transport to the approved packet and specimen: `binding()` must equal the packet route, wallet, app, per-specimen attempt identity and auth-header expiry.
3. Refuse a content-hash mismatch, an expired packet, a missing or non-separated policy owner, an unbound or unseparated profile policy, an unqualified mandatory control, an invalid proof scope, an invalid ceiling and an incomplete specimen manifest. A `TRADE` packet also refuses an unqualified position-inventory obligation; a `POLICY_LAYER` packet records that obligation at its true state and does not claim it.
4. Resolve the code-owned qualified profile.
5. Enforce the run time ceiling.
6. Check the accepted manifest, the specimen identity, the exact request bytes, the canonical headers and the request byte ceiling.
7. Keep type 4 `NOT_RUN` without a valid owner-bound authority.
8. Refuse any request outside the accepted type-2 `eth_signTransaction` profile with `REQUEST_PROFILE_UNQUALIFIED`. The accepted authorizer accepts only that narrow shape, so type 0, type 1, type 4 and `personal_sign` negatives stay refused/unqualified until a separately accepted route exists.
   Refuse any request whose destination is not the packet's single approved wallet route with `DESTINATION_UNQUALIFIED`. The `raw.foreign_wallet` negative targets another wallet, so it stays refused/unqualified under this route and is never reported from a callback-only double.
9. Refuse a terminal, uncertain, stopped or blocked attempt, or a positive control not bound to this packet, request and policy.
10. Claim the immutable one-use intent with `O_EXCL` and `fsync`.
11. Recheck the stop marker after the claim and before the send.
12. Send once. No retry, redirect, renewal, fallback, policy-administration or cleanup request exists.

## Capture and classification

The runner writes `<id>.capture.json` before it classifies the reply. The capture holds fixed metadata: status, media type, content-type SHA-256, byte count, raw-body SHA-256, metadata validity and the capture time. For an error reply (status 400 or above, bounded JSON) it also holds `error_code` and `error_type`, each only when it is letter words joined by underscores (at most 64 characters), else null; a reply below 400 is never parsed for the capture. It never holds reply text, headers, credentials, the authorization signature or signed bytes. On the control-proof expiry row, a 401 whose code says the request or its authorization signature expired is `UNKNOWN` / `EXPIRY_REFUSAL`; any other 401 is `UNRECOGNIZED_REPLY`. See `docs/qualification/inapp-trade/CONTROL_PROOFS_PLAN.md` (Finding 2) for the rule and the one-row expiry re-run.

The transport sends only `eth_signTransaction`, only to the exact approved wallet RPC URL, and uses a frozen `privy-request-expiry` header when the specimen carries one. A refusal before dispatch is `OPERATION_NOT_APPROVED`, `DESTINATION_NOT_APPROVED` or `TRANSPORT_REFUSED`. Every transport failure is raised outside its handler, so no provider or authorizer text remains in `__cause__` or `__context__`.

A qualified profile classifies the reply. It reads the error code from `code`, `error.code` or the string `error`, and never keeps other reply text. A success on a negative specimen is `BREACH`. A signed-field mismatch from the accepted `validate_signed` decoder is `BREACH`. An unrecognized code, a generic 403, an HTML challenge, malformed metadata, an oversized reply, a deep reply, a decode failure or a lost reply stays `UNKNOWN` and stops later specimens. An expected expiry stays `UNKNOWN` with reason `EXPIRY_REFUSAL` and does not stop.

The outcome and capture records carry the exact admitted request hash, the packet, the reply profile, the policy id and the policy content hash. The profile positive control is accepted only when its saved ALLOW binds to the currently admitted packet, positive request and policy. A stale, synthetic, corrupt or mismatched positive control is refused.

The runner is fail-closed across stop, outcome and capture write failures. If the stop marker cannot be written after an `UNKNOWN` or `BREACH`, the runner keeps the intent unresolved or recognizes a saved terminal `UNKNOWN`, so a later specimen is refused with `UNRESOLVED_ATTEMPT_IN_STORE` or `STOPPED_AFTER_UNKNOWN` and no second send happens.

The outcome record keeps `evidence_class` `LOCAL_TESTED` and `provider_proof` `UNQUALIFIED`.

## Accepted helpers reused

- `scripts.privy_unfunded_proof.specimens.AttemptStore` for the durable store; the new `claim_record` method is a minimal extraction that keeps `claim` behavior unchanged.
- `scripts.privy_unfunded_proof.specimens.FROZEN_TABLE` for the accepted specimen matrix.
- `edge_os_api.execution.original_transaction.validate_signed` as the accepted signed-field decoder.
- `edge_os_api.research_history.http_clients.http_transport.HttpTransport` and `HttpResponse` as the HTTP seam.
- `edge_os_api.execution.privy_signer.make_p256_authorizer` as the production authorizer for the injected `authorize` callable.

## Resolved shared decoder dependency (gate F6)

The accepted Phase B `original_transaction.validate_signed` helper now requires the complete expected key set, the complete decoded key set and the exact value types before it compares any field. The raw profile `privy.raw.v1` binds that helper as its qualified decoder. Do not register an arbitrary callable as a qualified decoder.

## Frozen policy-layer packet

`UNFUNDED_POLICY_PACKET.md` freezes the one registered packet for the real policy `c30racyru6duaipj815cvjce`. It holds 19 ordered `eth_signTransaction` rows: four allows and fifteen policy-owned negatives. The first row is the positive control. The first negative is a chain-143 request and is the reply-shape bootstrap. The packet uses one profile (`raw`) and one policy, because the real setup has one policy and the proof uses raw-byte binding only. The four `executeSwap` rows use the five-field selector `0xce1e7030`; the receiver refusal row uses `0x31343b21`.

The packet and its table are sealed to reviewed SHA-256 literals. The registry admits the built packet only when its recomputed hash equals the literal; a source edit leaves the registry empty and every actual run refuses. The same rule binds the table manifest. Exactly one packet is approved. Packet v3 binds the tightened live R3 policy (function `executeSwap` only) and keeps the v2 rows. The packet hash is `8255d003097fd1a0216a6b64c48637f2ef745c7ebbe73035d0b8929403500528`; the table manifest is `f485816e431aae37e30d062df038a3e1d62b8cdadac8e510ebb5d0181c827b63`; the policy body hash is `61860d201ecd9ce6d92bff5e7c2122b40164ecb69d1fa375738cb67b17b0892b`. Packets v1 and v2 are refused. Packet v3 runs `raw.deny_plain_mon_transfer` before the slow `raw.deny_swap_with_mon`.

The packet scope is `POLICY_LAYER`. Controls enforced by the host, the Kuru contract or a later stage stay at their true states and do not block this narrow proof. A successful swap signature is not a trade approval.

Five deposit rows carry a value above `2**53 - 1` wei. The accepted signer and the transport now send such a quantity as a canonical lowercase `0x` string with no leading zeros, and keep a smaller quantity as a JSON number. `chain_id` stays a JSON number in the safe-integer range. The packet's request bytes are the wire form. The signed-field check decodes the wire value back to the exact integer, so a one-wei difference is `SIGNED_VALUE_MISMATCH` and a `BREACH`.

## Operator command

`python -m scripts.privy_unfunded_proof.actual_run --dry-run` validates and lists the packet without a credential, socket or file effect.

The live command needs `PRIVY_APP_ID`, `PRIVY_APP_SECRET`, `PRIVY_AGENT_KEY_FILE`, a new `--store` directory and `--confirm-unfunded` after an independent zero-balance read. It runs the frozen order one specimen at a time, stops on the first `BREACH`, `UNKNOWN` or mismatch, and never retries or broadcasts.

## Per-request time bounds

Each specimen gets one absolute 60 s request deadline. The TCP connect is bounded by the 15 s connect timeout, and it never exceeds the remaining request deadline. The TLS handshake, the request write and every response read use the remaining per-request deadline as their socket timeout. The accepted shared transport watchdog still shuts the socket at the absolute deadline, so a paced peer cannot extend the call.

A reply that starts after the connect timeout but inside the request deadline is accepted. A reply after the deadline stays `UNKNOWN` with reason `SEND_LOST`. There is no retry, resend, redirect, renewed idempotency key or deadline change.

The suite reproduces the v2 fault with a local fake Privy server that replies after the connect timeout. It also asserts the deadline still cuts a later reply and that the TCP connect never takes longer than its own bound.

## Limits

Local PASS proves the runner machinery and its refusal and recovery behavior over injected doubles. It does not prove Privy policy enforcement, an actual provider reply, key custody, wallet or policy administration, an actual signed transaction or any onchain effect.

The live run needs the frozen inputs in `ACTUAL_PROOF_OPERATION_INPUTS.json` and the recorded operator grant. It does not follow from this document. The packet expires at `1793836800`.
