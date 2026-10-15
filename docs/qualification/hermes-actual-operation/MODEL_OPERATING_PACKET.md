# Model operating packet: one actual Hermes request (prepared, NOT approved, NOT run)

Task `HERMES-OPERATOR-L1-20261015-LOCAL-v1`. Status: PREPARED FOR BUILDER REVIEW. This packet authorizes nothing. No key or account was read and no provider request was made to prepare it. A real request needs, in order: the open facts in section 6 proved, an exact release record and price snapshot frozen, a reviewed code change that adds that record's SHA256 to `APPROVED_ACTUAL_RELEASES`, lane-2 composition accepted, and an explicit builder approval of this packet's final values.

It reuses the closed Probe A handling (`../hermes-provider-relay/PROBE_A_PROVIDER_REUSE.md`, `../../prototypes/EDGE_OS_PROBE_A_RESULT.md`) and does not reopen that probe.

## 1. Documentation facts (Context7, 2026-10-15) and what they do not prove

Fetched from `/openrouterteam/docs` and `/websites/openrouter_ai`. Documentation is not provider or account proof.

| Fact | Source page |
|---|---|
| `POST https://openrouter.ai/api/v1/chat/completions`; `provider` object fields `only`, `allow_fallbacks` (default true), `require_parameters` (default false), `data_collection` (`allow`/`deny`, default allow), `zdr`, `max_price` | guides/routing/provider-selection |
| `max_price` is in USD per million tokens: `{"prompt": 1, "completion": 2}` routes only to endpoints priced at most USD 1/M prompt and USD 2/M completion; `request` and `image` keys also exist | guides/routing/provider-selection |
| Non-streaming responses carry `usage` (`prompt_tokens`, `completion_tokens`, `total_tokens`, `cost`); counts use the model's native tokenizer and billing uses them | api_reference/overview, cookbook/usage-accounting |
| `GET /api/v1/generation?id=<generation id>` returns token counts and cost after the request | api_reference/overview |
| Model and endpoint pricing (`/api/v1/models`, `/api/v1/models/{author}/{slug}/endpoints`) is per token in USD strings; pricing may also carry `internal_reasoning`, `input_cache_read`, `input_cache_write`, `discount`, `request` and conditional `overrides` (long-context or time windows); the documented examples send an `Authorization` header | models and endpoints API reference, SDK `PublicPricing` |
| Model variants such as `:floor` can admit discounted flex endpoints | guides/routing/model-variants/floor |

NOT VERIFIED by documentation: that `openai/gpt-6.1-sol` exists now, its endpoints, provider slugs, current prices, `data_collection: deny` compliance, supported parameters (`reasoning`, `response_format`, `max_tokens`) or maximum output. The builder preference (OpenRouter, `openai/gpt-6.1-sol`) is an input, not proof. Probe A observed `openai/gpt-6.1-sol` with requested route `openai/flex`, low reasoning and `max_tokens` 4096 on its own dated run (R1 9,511/1,957 tokens USD 0.021673; R2 9,903/3,312 tokens USD 0.028938). Those are dated observations, not current prices.

## 2. Frozen request shape (release record fields, CONTRACT A6)

| Record field | Value | Status |
|---|---|---|
| `kind`, `stream` | `ACTUAL`, `false` | fixed by code |
| `destination` | `openrouter.ai`, 443, `/api/v1/chat/completions` | fixed by code |
| `model` | `openai/gpt-6.1-sol` | builder input; availability open (6.1) |
| `provider.only` | exactly one slug from the current endpoints list | open (6.1); Probe A's `openai/flex` is dated |
| `provider.allow_fallbacks`, `require_parameters`, `data_collection` | `false`, `true`, `"deny"` | fixed; `deny` support for the slug open (6.2) |
| `provider.max_price` | `{"prompt": P, "completion": C}` equal to the snapshot rates (USD per million) | open (6.1); see section 3 |
| `max_tokens` | 4096 | equal to the application interpreter limit (lane 2 checks) |
| `reasoning` | `{"effort": "low"}` | Probe A value; support open (6.2) |
| `response_format_sha256` | SHA256 of the accepted application interpreter output schema (canonical JSON) | lane 2 supplies; no fixture schema |
| `allowed_fields` | `model, messages, stream, response_format, provider, reasoning, max_tokens, session_id` | fixed by A6 |
| `max_request_bytes` | 65,536 | ONLINE_CONTINUATION section 3 (Probe A about 34 KB) |
| `max_reply_bytes` | 262,144 | ONLINE_CONTINUATION section 3 (Probe A up to about 17 KB) |
| `timeout_seconds` | 90 (grant life; must be 1-120) | Probe A C2 calls: 24.2 and 38.5 s in `PROBE_A_PROVIDER_REUSE.md`, 26.104 and 40.088 s in the result table |
| `ca_bundle_sha256` | SHA256 of the frozen public CA bundle file the relay trusts for `openrouter.ai` | open (6.4) |
| `price_snapshot_sha256` | SHA256 of the lane-2 snapshot (exact model, provider slug, prompt/completion USD per million as decimal strings) | open (6.1) |
| `approval` | `{path, sha256}` of the builder's signed-off final packet | open |

Session id is bound to `p05-<attempt>` by the relay. No tools, memory, fallback model or retries (accepted job configuration).

## 3. Spending: one request, one reservation, full liability

- Maximum actual requests: **1** for this qualification. After it, stop, whatever the outcome.
- One reservation before the grant (accepted `GuardedTurnRunner` and `PostgresSpendLedger`): `max_input_tokens = max_request_bytes + 64` (`INPUT_TOKEN_MARGIN`), `max_output_tokens = max_tokens`. Liability in USD = `(65,600 × P + 4,096 × C) / 1,000,000`, with P and C the snapshot rates in USD per million.
- Set `max_price` equal to the snapshot rates. By OpenRouter's documentation, routing then skips endpoints priced above those rates. This is documented provider behaviour, not enforcement this system proves.
- Ceiling: the model and the data work together may use at most **USD 2.00**, counting every reservation, settled charge and UNKNOWN liability already recorded. The model reservation must not exceed the model share the builder assigns from that USD 2.00; this packet does not choose the share. Trading and gas have their own separate USD 2.00 and are not part of this packet. Example only, not a price: P = 2, C = 8 gives USD 0.1312 + 0.032768 = USD 0.163968.
- Counted result (E1-COST1): 2xx, one choice, `finish_reason` `stop`, the record's model, integer usage equal to the job's, and the provider `cost` rounded up to a nano-USD EQUAL to `TokenPrice.nano_usd(prompt, completion)` and at most the reservation. Anything else is UNKNOWN: text withheld, never resent, the full reservation stays.
- Known gap: cached-prompt discounts, reasoning-token rates, request fees, discounts and conditional overrides are not in the two-rate `TokenPrice`. If any applies, the cost will not equal the token charge, and the result stays UNKNOWN with full liability. That is safe but does not settle. Settling those needs a later ledger-owner change.

## 4. Independent evidence for the one request

| Count | Where | Expected |
|---|---|---|
| relay start records | `<run root>/relay/state/<attempt>/started.json` | 1 |
| gateway tunnels | `<run root>/relay/gateway/receipts/tunnels.jsonl` `opening` lines for the attempt | 1 |
| provider generation | `finished.json` `generation_id`, `usage`, `cost` | 1 id |
| ledger | the attempt's reservation and settlement rows | RESERVED then settled at the token charge, or UNKNOWN |

The generation lookup (`GET /api/v1/generation?id=`) is a separate host-held, key-using operation. It needs its own approval and is not part of the relay or this request. Record the account's credit usage before and after only if the builder approves that account read.

## 5. Stop and recovery

1. Before the request: `relay_operator.py CONFIG check`, then `start`; record the printed handoff hash.
2. After the one request, or on any failure or timeout: no second request. `relay_operator.py CONFIG stop`; exit 0 needs no leftovers and no foreign object. Stop needs only the configuration file and the run root, not the key file.
3. Relay killed after start: `restart` only to let recovery C mark `unknown_restart`; nothing is resent. The attempt stays UNKNOWN.
4. Host killed mid-turn: the application's `recover_pending` handles the job; the reservation stays.
5. Any UNKNOWN blocks further actual requests until a separately approved reconciliation (generation lookup) records the real charge.
6. Keep the run root, receipts and ledger rows as evidence. Scan them for the key before any publication.

## 6. Open facts (labelled, not invented)

1. Current model existence, endpoint list, one provider slug and its exact current prompt and completion prices, plus any reasoning, cache, request or override pricing (a public models/endpoints read; whether it needs a key is open).
2. That slug's support for `data_collection: deny`, `require_parameters` with `reasoning`, `response_format` and `max_tokens` 4096.
3. Account facts: key existence and scope, credit balance, spend limits, fees. Not read here.
4. The CA bundle file and its SHA256.
5. The builder's model share of the combined USD 2.00 ceiling, and the spend already recorded against it.
6. Application facts owned by lane 2: interpreter schema hash, prompt size against 65,536 bytes, and trusted definition and price snapshot binding.
