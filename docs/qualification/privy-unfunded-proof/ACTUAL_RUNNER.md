# Local unfunded actual proof runner

Task `ACTUAL-POLICY-PROOF-L3-20261018`. Status `LOCAL`. Provider proof `UNQUALIFIED`. Every result is `LOCAL_TESTED`.

This document describes the successor of the accepted synthetic driver. It does not approve any actual packet, profile, route, policy or provider request. It does not permit funding.

## Files

| Path | Responsibility |
| --- | --- |
| `scripts/privy_unfunded_proof/actual_packet.py` | The frozen exact actual packet, the twelve P21 controls, the position-inventory obligation, the type-4 authority gate and the code-owned approval registry. |
| `scripts/privy_unfunded_proof/actual_profile.py` | The qualified reply/decoder profile and its code-owned registry. |
| `scripts/privy_unfunded_proof/actual_transport.py` | One-shot bounded sign-only transport to the exact approved destination. |
| `scripts/privy_unfunded_proof/actual_runner.py` | `run_actual_specimen`: admission, one-use intent, bounded capture, classification and stop. |
| `tests/privy_unfunded_proof/test_actual_proof_runner.py` | Offline regression evidence. |
| `tests/privy_unfunded_proof/_actual_support.py` | SYNTHETIC doubles used only by these tests. |
| `docs/qualification/privy-unfunded-proof/ACTUAL_PROOF_OPERATION_INPUTS.json` | The exact missing external inputs. |

## Default refusal

The code-owned registries are empty. Therefore a default actual run refuses with `ACTUAL_PACKET_NOT_APPROVED` before any credential read, socket or file effect.

A caller cannot approve a packet with a Boolean, function argument, flag or environment setting. `run_actual_specimen` takes no approval, profile or authority mapping. Resolution reads only `CODE_OWNED_PACKET_APPROVALS`, `QUALIFIED_ACTUAL_PROFILES` and `CODE_OWNED_TYPE4_AUTHORITIES`. The same rule applies to every entry.

The synthetic driver keeps its boundary. `run_specimen` still accepts only `SYNTHETIC_FIXTURE`, and `ACTUAL_RUN_REFUSED` is unchanged.

## Admission order

1. Resolve the code-owned packet.
2. Bind the transport to the approved packet and specimen: `binding()` must equal the packet route, wallet, app, per-specimen attempt identity and auth-header expiry.
3. Refuse a content-hash mismatch, an expired packet, a missing or non-separated policy owner, an unbound or unseparated profile policy, an unqualified mandatory control, an unqualified position-inventory obligation, an invalid ceiling and an incomplete specimen manifest.
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

The runner writes `<id>.capture.json` before any JSON parse. The capture holds only fixed metadata: status, media type, content-type SHA-256, byte count, raw-body SHA-256, metadata validity and the capture time. It never holds reply text, credentials, the authorization signature or signed bytes.

The transport sends only `eth_signTransaction`, only to the exact approved wallet RPC URL, and uses a frozen `privy-request-expiry` header when the specimen carries one. A refusal before dispatch is `OPERATION_NOT_APPROVED`, `DESTINATION_NOT_APPROVED` or `TRANSPORT_REFUSED`. Every transport failure is raised outside its handler, so no provider or authorizer text remains in `__cause__` or `__context__`.

A qualified profile classifies the reply. A success on a negative specimen is `BREACH`. A signed-field mismatch from the accepted `validate_signed` decoder is `BREACH`. An unrecognized code, a generic 403, an HTML challenge, malformed metadata, an oversized reply, a deep reply, a decode failure or a lost reply stays `UNKNOWN` and stops later specimens. An expected expiry stays `UNKNOWN` with reason `EXPIRY_REFUSAL` and does not stop.

The outcome and capture records carry the exact admitted request hash, the packet, the reply profile, the policy id and the policy content hash. The profile positive control is accepted only when its saved ALLOW binds to the currently admitted packet, positive request and policy. A stale, synthetic, corrupt or mismatched positive control is refused.

The runner is fail-closed across stop, outcome and capture write failures. If the stop marker cannot be written after an `UNKNOWN` or `BREACH`, the runner keeps the intent unresolved or recognizes a saved terminal `UNKNOWN`, so a later specimen is refused with `UNRESOLVED_ATTEMPT_IN_STORE` or `STOPPED_AFTER_UNKNOWN` and no second send happens.

The outcome record keeps `evidence_class` `LOCAL_TESTED` and `provider_proof` `UNQUALIFIED`.

## Accepted helpers reused

- `scripts.privy_unfunded_proof.specimens.AttemptStore` for the durable store; the new `claim_record` method is a minimal extraction that keeps `claim` behavior unchanged.
- `scripts.privy_unfunded_proof.specimens.FROZEN_TABLE` for the accepted specimen matrix.
- `edge_os_api.execution.original_transaction.validate_signed` as the accepted signed-field decoder.
- `edge_os_api.research_history.http_clients.http_transport.HttpTransport` and `HttpResponse` as the HTTP seam.
- `edge_os_api.execution.privy_signer.make_p256_authorizer` as the production authorizer for the injected `authorize` callable.

## Unresolved shared decoder dependency (gate F6)

The accepted `original_transaction.validate_signed` helper compares selected decoded fields and does not yet validate the complete decoded key set or exact value types. That helper is outside this worker's lease and stays unchanged. No decoder is registered as fully qualified, so `QUALIFIED_ACTUAL_PROFILES` stays empty and an actual run refuses. The qualification is completed by the PhaseB owner through a recorded accepted-helper handoff; do not register an arbitrary callable as a qualified decoder.

## Limits

Local PASS proves the runner machinery and its refusal and recovery behavior over injected doubles. It does not prove Privy policy enforcement, an actual provider reply, key custody, wallet or policy administration, an actual signed transaction or any onchain effect.

A future actual run needs the frozen inputs in `ACTUAL_PROOF_OPERATION_INPUTS.json` and a separate release. It does not follow from this document.
