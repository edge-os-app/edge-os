# Hermes provider relay: LOCAL results and how to check them

Task `HERMES-RELAY-L1-20261013-LOCAL-v1` (#58 support). Status: LOCAL, synthetic credential, AUTHORED provider. ACTUAL provider, network, billing, deployment and production hosting: NOT_RUN. This folder gives no authority.

| File | What it holds |
|---|---|
| `CONTRACT.md` | The frozen boundary: files, interfaces, grant and channel shapes, records, settlement table, fault matrix, seams, amendments. |
| `README.md` | What the local tests show, what they do not show, and how to run them. |

## 1. What the relay changes

Before: the accepted transport job runs Hermes, the transport and a credential copy in one process (`docs/qualification/hermes-job-support/README.md` section 1). Now: the Hermes job has no credential mount and no network; its one admitted request goes as a file into its own output folder; a separate relay container, on an internal Docker network shared only with the AUTHORED provider, checks a host-signed grant, runs the accepted guard again on the exact bytes, records a start before the one HTTPS request, and returns a bounded reply. The relay's records and the provider's receipts count requests outside the job. Details: `CONTRACT.md`.

## 2. What the local tests show

Synthetic key `sk-test-RELAY-SENTINEL-...`, authored provider, test CA. `tests/hermes_provider_relay/`:

- `test_relay_admission.py` (no Docker): grants are signed over every identity; a grant changed after signing (another owner, request, attempt or expiry), signed with another key, for another release, expired or not yet valid admits nothing; channel messages with another attempt, route or release, any extra field (URL, header, credential), a body that is not base64 or too large are refused; ACTUAL releases cannot be expressed.
- `test_relay_turn_runner.py` (no Docker): construction does no I/O; ACTUAL routes refused with or without a release; no grant without a recorded reservation, a proved owner/request and a live relay of the same release (all released, no job); an existing grant is never replaced (UNKNOWN); a zero-request result is released only with the relay's closed-not-started record; any job report the relay record does not support (hidden request, phantom request, other usage, lost reply, no close record) is withheld as UNKNOWN with the full reservation; a raising job still revokes its grant.
- `test_relay_service.py` (relay and provider as loopback host processes; egress NOT enforced here): one request with the relay key and its reply; forged, cross-owner, stale and other-release grants; cancellation before and after a possible send; altered attempt/route/release/header/URL/model/stream/output-limit/routing fields; malformed, duplicate-key and oversized files; linked request files; two channels for one attempt; a planted reply link never written through; duplicate and restarted requests sent once; a relay killed after a possible send never resends and reports `unknown_restart`; oversized, redirect and streaming replies dropped but counted; lost replies; a request with no grant ignored; a new grant served after 1,100 closed ones; no record holds the key.
- `test_relay_through_pinned_hermes.py` (ACTUAL pinned Hermes, Docker): one request through the relay, every identity equal to the attempt, the provider sees the relay's bearer and none of Hermes' headers, exact charge, relay usage equals job usage; job guard refusal released on the relay's closed-not-started record; relay down: no grant, no job, released; lost, oversized, redirect, provider error and missing usage keep the full reservation with relay and provider counts (1, 1); a hung provider is cut at the grant expiry and the job at D; a relay crash after the request never resends; two attempts at once keep their own grants and charges; a hostile job finds no key file or key environment and no network path (provider, relay, 1.1.1.1, host), and its altered model/route/release/attempt/header/URL/oversized channel messages are refused before any request, its duplicate sent once; the relay has only the internal network (only relay and provider on it, no published port, exact mounts) and its egress self-probe reaches only the provider; a host killed mid-turn is recovered within C, its grant closes at expiry, its reservation stays and blocks its scope; no evidence, record or log holds the key.
- `test_relay_application_mount.py` (application, PostgreSQL, Docker): `create_app` over `open_relay_mount`: a saved request goes through the relay once, is charged exactly in the shared ledger, the grant names the SQL owner and saved request, it reopens identically from another application instance and is 404 to another owner; a lost reply is never accepted, keeps the reservation, and its retry is refused (409) with no new grant.

Not shown: a real provider, model, network, DNS/TLS to a public host, prices, provider-side billing stop, deployed egress enforcement (Contabo or any host), a separately supervised production relay, multi-host clocks, or the shared default verifier (lane 2 owns it; a map proposal is in the return packet).

## 3. How to check

From `apps/api`, with the locked environment. Use `.venv/bin/python -m pytest`: a cloned environment's `pytest` script can start another checkout's interpreter.

```
.venv/bin/python -m pytest -p no:cacheprovider -q ../../tests/hermes_provider_relay/test_relay_admission.py ../../tests/hermes_provider_relay/test_relay_turn_runner.py ../../tests/hermes_provider_relay/test_relay_service.py
HERMES_RELAY_EVIDENCE_DIR=<private folder> .venv/bin/python -m pytest -p no:cacheprovider -q ../../tests/hermes_provider_relay
```

The second command needs Docker and the pinned Hermes checkout (see `docs/qualification/hermes-job-support/README.md` section 4). It builds the pinned image, starts its own internal networks, relays and providers by exact name and label, and removes them; `relay-cleanup.json`, `app-relay-cleanup.json` and `image-cleanup.json` in the evidence folder must show nothing left. About five minutes.
