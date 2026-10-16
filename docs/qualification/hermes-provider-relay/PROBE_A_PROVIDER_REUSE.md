# Probe A provider protocol: sanitized reuse extract for the relay

Task `HERMES-RELAY-L1-20261013-LOCAL-v1` (#58/P05), online continuation preparation. This extract gives no authority. It holds no credential, request text, prompt, response text, account detail or private market input. Prices, model availability and routing below are dated observations from a closed probe, not current configuration proof.

Sources (builder-only, read-only; not rerun): `edge-os/docs/prototypes/EDGE_OS_PROBE_A_RESULT.md` (SHA256 `d9ef658c...`), `prototypes/edge-os/probe-a/interpret_1b.py` (`a15ae4f7...`: `validate_request`, `make_agent`, `Gate.handle_request`), `prototypes/edge-os/probe-a/research_c2.py` (`1aaee560...`: `configure_adapter`, `delivered`, `execute_call`, `Accounting`), and the C2 `R1`/`R2-dispatch-01` HTTP, request and response receipts. Pins: `.scratch/hermes-prototype-to-application-20261014/SOURCE_IDENTITIES.json`.

## 1. What a real run already showed

- Pinned Hermes `54bc5e509c985f37265c3d416bd2c64b10fc77ba` completed real OpenRouter conversations: five interpretation/clarification cases and two C2 research calls. Cumulative 28 model calls, USD 0.0814978625, zero outstanding reservations.
- C2 calls: model `openai/gpt-6.1-sol`, routing `openai/flex`, low reasoning, `max_tokens` 4096, strict JSON schema output. R1 24.2 s, R2 38.5 s; both HTTP 200 and `finish_reason` `stop`.
- Request bodies were about 29-34 KB as stored; decoded replies were about 8-17 KB.

Do not repeat a provider feasibility probe for these facts. A new request still needs current configuration proof and its own approval.

## 2. Request rules to keep (from `validate_request` and `make_agent`)

| Rule | Prototype behavior | Relay equivalent |
|---|---|---|
| One fixed endpoint | `POST https://openrouter.ai/api/v1/chat/completions` only, checked on the URL | `ProviderDestination("openrouter.ai", 443, "/api/v1/chat/completions")`, fixed in the release; the job gives no URL |
| Allowed body fields | `model`, `messages`, `stream`, `response_format`, `provider`, `reasoning`, `reasoning_effort`, `max_tokens`; no `temperature` | the accepted guard plus a release-pinned field set; also `session_id` (see 4) |
| Model and output | exact model; `stream` false; `max_tokens` equal to the cap | `RelayRelease.model`, `max_output_tokens`; guard refuses any other value |
| Routing | `provider = {only: [one slug], allow_fallbacks: false, require_parameters: true, max_price: {...}}`, exact equality | the routing object is part of the release and checked by exact equality on the admitted bytes |
| Reasoning, schema | exact `reasoning` object and `response_format` | exact equality; the schema is pinned by hash in the release |
| No retries | SDK `max_retries=0`, `httpx` `retries=0`, one API attempt, recovery cycles 0 | `send_once`: one connection, no retry; the relay never resends an attempt |
| No redirects, no proxy from the environment | `follow_redirects=False`, `trust_env=False` | 3xx reply refused (`reply_redirect_refused`); `send_once` reads no proxy variables |
| Context | no tools, memory, context files, soul file, fallback model or compression | unchanged accepted job configuration |
| Key | key read from a 0600 file in a 0700 folder; never in the prompt; reply checked for the key | key file mounted read-only into the relay only; the job never holds it; leak scan on records |

## 3. Reply and accounting lessons

- Truncation and format: a reply with `finish_reason` `length`, more than one choice, or a non-final reply was refused before Hermes could continue. Keep: the counted result needs one choice with `stop`, then the application's own output validation.
- Compression: the provider sent `content-encoding: gzip` and chunked transfer because the prototype's client asked for gzip. `send_once` sends no `Accept-Encoding`. A reply that is still encoded must be refused as a counted request (liability held), not decoded on trust.
- Usage: replies carried `usage.prompt_tokens`, `completion_tokens`, `total_tokens` and a provider-reported `cost` (USD) with a cost breakdown. Settlement used the reported cost.
- Reservation: before the request, a conservative bound from a stored endpoint price snapshot: (request bytes + 2048 framing) × the highest prompt/cache rate + 4096 × the completion rate, checked against the remaining allowance.
- Unknown charge: a reservation without settlement blocked every later call (`UNKNOWN_CHARGE_STOP`) until reconciled. Keep this rule; the shared PostgreSQL ledger already holds UNKNOWN liability.
- Sticky routing: pinned Hermes adds `extra_body.session_id`. The prototype removed it from its minimal packet. OpenRouter documents `session_id` as a sticky routing field. The relay keeps it and binds it to `p05-<attempt>`.

## 4. What does not transfer

- The prototype's key and HTTP transport ran inside the Hermes process. Its network control was a Python socket monkey-patch, not operating-system isolation. The relay replaces this with a keyless no-network job and a separate key holder.
- Its accounting was a single-process file journal, not the shared multi-owner ledger.
- Its five semantic PASS results used the probe's prompt and response contract. The application's contract is different, so they do not approve the application's prompt.
