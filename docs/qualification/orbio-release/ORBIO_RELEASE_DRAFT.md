# Orbio release draft: one record and one price table (prepared, NOT approved, NOT active)

Task `CLOUD-ORBIO-RELEASE`, builder-approved normal cloud session, 2026-10-22. Base `617b9e2add99305b3da1a94f80b8ca7ca1924c9d` (CLOUD-02, relay contract A8). Status: DRAFT FOR BUILDER REVIEW.

This draft approves nothing. No key was read, no request was sent to Orbio (not even a public catalogue read or a TLS handshake), and nothing was bought. The one approved ACTUAL release stays `hermes-first-call-1` on OpenRouter. Nothing selects the Orbio draft:

- its record SHA256 is not in `relay_admission.APPROVED_ACTUAL_RELEASES`, so `load_actual_release` refuses it with `ActualReleaseUnapproved`;
- it has no entry in `hermes_relay_composition.RELEASE_DEFINITIONS`, whose docstring makes adding one a reviewed code change together with the registry entry, so the draft is a docs-only record;
- even if its hash were approved, the current loader refuses it, because it names no routing object (section 3.2).

No relay, gateway, supervisor, operator, admission or application code changed. The OpenRouter record, approval packet, price snapshot and the CLOUD-02 golden bytes are unchanged.

## 1. Source facts (public Orbio documentation, read by the builder 2026-10-22)

The facts below were given by the builder from Orbio's public documentation on `orbio.so`, read 2026-10-22. This session did not fetch them. Look-alike sites `orbioagent.world` and `orbio-proposals.xyz` are not Orbio and are not sources.

| Fact | Status |
|---|---|
| Orbio relays requests to "Orbio's managed OpenRouter account" | documented |
| OpenAI-compatible chat completions: `POST https://api.orbio.so/api/v1/chat/completions` (port 443). The agent guide also uses `https://www.orbio.so/api/v1` | documented |
| Authentication: `Authorization: Bearer sk-orbio-...` | documented |
| Unsupported sampling parameters are dropped and named in the `X-Orbio-Ignored-Parameters` response header | documented |
| An `X-Orbio-Balance` response header | documented |
| `GET /api/v1/key` returns balance, usage and rate limits (example: 120 requests per minute, 32 concurrent) | documented |
| Public catalogue of 450 models. Ids and prices are identical to OpenRouter's. Free models are excluded | documented |
| 78 models have price overrides by token count or by UTC time of day, for example `claude-haiku-5.5` and `deepseek-v4.1-flash-1017` | documented |
| TLS: Let's Encrypt. `api.orbio.so` is issued by YR1, `www.orbio.so` by YR2. Both chain to ISRG Root YR, which ISRG Root X1 cross-signs | documented |

UNKNOWN (not documented, not tested, not assumed below):

1. Whether replies include `usage.cost`, and what it means: Orbio's charge, OpenRouter's upstream charge, or something else.
2. Whether a cost lookup endpoint exists, like OpenRouter's `GET /api/v1/generation?id=`.
3. Whether OpenRouter's `provider` routing object is forwarded, dropped or rejected.
4. The exact reply `model` field and any provider fields in the reply.
5. Orbio's terms of service and privacy policy, including data retention and whether the upstream data-collection setting can be controlled.
6. Whether `openai/gpt-6.1-sol` is listed now, at what price, and whether it is one of the 78 override models. The catalogue rule (identical to OpenRouter) implies USD 2 / 10 per million only if it has no override. This session did not read the catalogue.
7. Whether `reasoning`, `response_format`, `max_tokens` and `prompt_cache_options` are forwarded or dropped. Only "sampling parameters" are documented as dropped.
8. Whether `api.orbio.so` serves the ISRG Root YR cross-certificate signed by X1, which a trust store holding only X1 needs.
9. Whether the `X-Orbio-Balance` value on a reply is read before or after that reply's charge, and its precision.

## 2. The draft record

Files in this folder:

| File | SHA256 | Meaning |
|---|---|---|
| `orbio_draft_record.json` | `8c39196ef2214ee74c42989f03eccbd9be72d4a6d1421c9f845582f427db2d78` | the draft ACTUAL record, canonical JSON in the CLOUD-02 shape |
| `orbio_draft_packet.json` | `992323624c97bb858d8259005b24893ea1277c19eb1cd6ffb71366ce90fc75ea` | status `DRAFT_NOT_APPROVED`; the record's `approval` names it. The record values, inputs and open facts |
| `orbio_draft_prices.json` | `eaa1ad5580c7b1a0296d8830fdbeaeb28ba0d39fb483144e1108ad6db71ae16f` | the draft price snapshot |
| `orbio_ca_isrg_root_x1.pem` | `22b557a27055b33606b6559f37703928d3e4ad79f110b407d04986e1843543d1` | the CA bundle: ISRG Root X1 only |

The record is the adopted OpenRouter record (`hermes-first-call-1`) with these differences only:

| Field | OpenRouter (approved) | Orbio draft | Why |
|---|---|---|---|
| `release_id` | `hermes-first-call-1` | `orbio-draft-1` | a draft name; it is not an approved identity |
| `route_id` | `openrouter-openai-standard` | `orbio-openrouter-managed` | |
| `destination` | `openrouter.ai`, 443, `/api/v1/chat/completions` | `api.orbio.so`, 443, `/api/v1/chat/completions` | the documented API host. `www.orbio.so` is not used: a release has one host, and the gateway admits only that host |
| SNI and verified name | `openrouter.ai` | `api.orbio.so` | A8: the TLS server name is the record's host. The record has no separate SNI field |
| `provider` (routing) | `only: [openai]`, no fallbacks, required parameters, `data_collection: deny`, `max_price` 2/10 | `null` (no routing fields) | forwarding of the routing object is UNKNOWN (1.3). Naming it would claim a provider pin, a privacy setting and a price ceiling that nothing shows Orbio applies |
| `allowed_fields` | includes `provider` | no `provider` | follows from no routing |
| `ca_bundle_sha256` | `7cef540c…` (OpenRouter's bundle) | `22b557a2…` (the ISRG Root X1 PEM above) | pin the root only |
| `price_snapshot_sha256` | `e53259b2…` | `eaa1ad55…` | snapshot names seller `orbio` (section 4) |
| `approval` | the adopted packet | the draft packet (`DRAFT_NOT_APPROVED`) | |

Unchanged: `kind` ACTUAL, `stream` false, `model` `openai/gpt-6.1-sol`, `max_tokens` 4096, `reasoning` `{"effort": "low"}`, `response_format_sha256` `cdffe6fd…`, `prompt_cache_options` `{"mode": "explicit"}`, `max_request_bytes` 65,536, `max_reply_bytes` 262,144, `timeout_seconds` 90.

CA pin. The bundle holds one certificate, ISRG Root X1. Its DER SHA256 fingerprint is `96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6`, which is Let's Encrypt's published value; the test checks it. The relay builds `ssl.create_default_context(cafile=<bundle>)` with no system store. So verification succeeds only if the server sends leaf → YR1 → ISRG Root YR (cross-signed by X1). No intermediate is pinned, and ISRG Root YR is not added as a trust anchor. Whether the cross-signed chain is served is UNKNOWN 1.8.

## 3. What the CLOUD-02 rules say about this record

Checked by `tests/hermes_provider_relay/test_orbio_release_draft.py`:

1. With the default registry, `load_actual_release(raw, sha)` raises `ActualReleaseUnapproved`. The hash check runs before any field is read.
2. With its hash injected as approved (test only), the loader still refuses it with `ValueError("routing must be an object")`. Two current rules stop an Orbio release that names no routing:
   - the loader requires a routing object with every known field (one provider, no fallbacks, required parameters, a price limit);
   - `REQUIRED_BODY_FIELDS` requires `provider` in every request body.
   `bind_release` also requires the price snapshot's `provider` to equal the routed provider `provider.only[0]`. So the draft snapshot's `provider: "orbio"` cannot bind under any record unless the routed provider is also named `orbio`. Three more places also read the routing object:
   - `_price` and `_rate` (`hermes_relay_composition.py`) cap the snapshot rates by `provider.max_price`;
   - `bind_release` builds `LiveRelease(provider=actual.provider["only"][0])`;
   - `ActualRelease.body_refusal` compares the request's `provider` field with the record's.
   This draft does not relax any of these rules. An Orbio release that names no routing needs a separately reviewed code change. That change must keep these rules unchanged for the OpenRouter record and keep its golden bytes.
3. Every other field meets the loader as written. The test swaps only the routing object for a synthetic one and loads the result under a test-only registry: destination `api.orbio.so:443/api/v1/chat/completions`, CA pin, release settings, reasoning, cache options and timeout all parse.
4. The adopted record, approval packet and price bytes keep their SHA256 values. `APPROVED_ACTUAL_RELEASES` is exactly `{3fa94dd7…}`, and `RELEASE_DEFINITIONS` has exactly that one definition. The CLOUD-02 golden test (`test_release_destination_golden.py`) still passes unchanged.

## 4. Price table rule

The draft price snapshot is:

```json
{"completion_usd_per_million":"10","model":"openai/gpt-6.1-sol","prompt_usd_per_million":"2","provider":"orbio"}
```

Rule. An Orbio snapshot may be adopted only with these rates, and only when all of these hold:

1. Orbio's public catalogue, read on the approval date from `orbio.so` itself, lists `openai/gpt-6.1-sol`.
2. It lists the same prompt and completion USD-per-million rates as OpenRouter's public price for that model on the same date.
3. Those rates equal the snapshot: USD 2 prompt, USD 10 completion.
4. The model has no token-count or time-of-day override, and no cache, reasoning, request or other fee.

Otherwise no Orbio release is drafted for that model. In particular, no rate is averaged, and no rate is picked as "the usual one" for an override model.

`provider` names the seller, `orbio`, because the upstream endpoint is not pinned. The ledger's two-rate `TokenPrice(2, 10)` is the same object for reservation, settlement and the relay cost check (E1-COST1). The worst-case reservation is the same as OpenRouter's: (65,600 × 2 + 4,096 × 10) / 1,000,000 = USD 0.17216 per request.

## 5. Settlement question

The application settles a counted reply only when (`relay_turn_runner._cost_equals_charge`, E1-COST1):

`ceil(usage.cost × 10^9)` nano-USD == `TokenPrice.nano_usd(prompt_tokens, completion_tokens)` = `prompt_tokens × 2,000 + completion_tokens × 10,000` nano-USD, and that charge is at most the held reservation.

The relay also requires these for a counted reply (`ActualRelease.reply_check`):

- status 2xx and `application/json`, with no content encoding;
- exactly one choice, with `finish_reason` `stop`;
- reply `model` exactly `openai/gpt-6.1-sol`;
- integer `prompt_tokens`, `completion_tokens` and `total_tokens`;
- a finite, non-negative numeric `usage.cost`.

Otherwise the attempt is UNKNOWN. The text is withheld, nothing is resent, and the full USD 0.17216 stays as liability.

The open question is whether Orbio's `usage.cost` exists and equals Orbio's own token-priced charge for this request. If it is OpenRouter's upstream cost, Orbio's markup or another figure, then equality with the token charge is a coincidence, not a settlement. One counted reply proves only one request.

## 6. Variable-price risk

- Override models. 78 models carry token-count or UTC time-of-day overrides. If `openai/gpt-6.1-sol` has one, or gains one after approval, the two-rate price is wrong at some times or sizes. A higher rate can make the real charge exceed the reservation. The ledger's liability then understates real spending against the shared USD 2.00 ceiling, which the relay cost check cannot see before the request is sent.
- No price ceiling on the wire. OpenRouter's `max_price` routing limit is what makes the provider refuse a pricier endpoint. With no forwarded routing object, nothing on the request bounds the price. Only the catalogue reading and the after-the-fact cost check remain.
- No provider pin. Without `only` and `allow_fallbacks: false`, Orbio's OpenRouter account may route to any endpoint for the model, at that endpoint's price and data policy. `data_collection: deny` is not applied.
- Catalogue drift. "Identical to OpenRouter" is a documented claim as of 2026-10-22, not a contract. Either side can change prices between the catalogue reading and the call.
- Failure mode. Every mismatch above makes the attempt UNKNOWN with full liability, so the ledger never settles low by mistake. The risk is a charge above the reservation, and a ceiling that can only be reconciled from the Orbio balance.

## 7. Approval steps for the builder

None of these are done. Each step is a separate builder decision.

1. Read Orbio's terms of service and privacy policy on `orbio.so` and accept or reject them (UNKNOWN 1.5).
2. Read the public catalogue on `orbio.so` for `openai/gpt-6.1-sol`. Record the date, the rates and whether it has any override. Compare it with OpenRouter's public price. Apply the section 4 rule. If it fails, stop.
3. Decide the routing question. Either:
   - (a) obtain Orbio's documented or tested behavior for the `provider` object, then redraft the record with the proved fields; or
   - (b) authorize a separately reviewed code change that admits a release naming no routing, without relaxing any OpenRouter check. It must cover every routing use in section 3.2, including the snapshot `provider` and `max_price` rules.
   Either way the record bytes, and so the SHA256, change.
4. Authorize a handshake-only TLS check of `api.orbio.so:443` with SNI `api.orbio.so` against this bundle, with no HTTP request. It must verify to ISRG Root X1 (UNKNOWN 1.8). If it does not, the pin must be redrafted.
5. Decide how the paid call observes `X-Orbio-Ignored-Parameters` and `X-Orbio-Balance`. The relay records no response header today. Either authorize a reviewed relay change that records those two named headers, or a separate builder-run observation.
6. Obtain an Orbio key, held only by the relay, and fund it. This is a paid purchase that needs explicit financial authorization. Decide its share of the shared USD 2.00 model and data ceiling.
7. Change the draft packet into an approval (`status`, final values, date and base). Re-hash the packet and then the record. Add the record's SHA256 to `APPROVED_ACTUAL_RELEASES` and its definition to `RELEASE_DEFINITIONS` in one reviewed change. The registries may hold at most one approved release. Decide explicitly whether Orbio replaces the OpenRouter release; it is never added beside it.
8. Authorize exactly one paid test call under the section 8 checklist. Integrate and merge only under the recorded main authorization.

## 8. Paid-call checklist (one request; nothing here is authorized)

Before the call:

- [ ] Steps 1 to 7 are done and recorded, the operator `check` passes, and the remaining-budget reconciliation shows room for USD 0.17216.
- [ ] `GET /api/v1/key` is read with the key (a separately approved key-using read). Record the balance B0, the usage and the rate limits.
- [ ] Record the call's UTC time, and confirm the catalogue rates for that model at that time are still USD 2 / 10 with no override.

The one call must observe all of these:

1. HTTP 200, `content-type: application/json`, and no `content-encoding`.
2. `X-Orbio-Ignored-Parameters` absent or empty. If it names `reasoning`, `response_format`, `max_tokens`, `prompt_cache_options` or any other sent field, the release shape is not honored.
3. One choice with `finish_reason` `stop`, and reply `model` exactly `openai/gpt-6.1-sol`. Record any provider field in the reply (UNKNOWN 1.4).
4. Integer `usage.prompt_tokens`, `completion_tokens` and `total_tokens`, equal to the job's counts.
5. `usage.cost` present and numeric, with `ceil(cost × 10^9) == prompt_tokens × 2,000 + completion_tokens × 10,000` nano-USD and at most 172,160,000 nano-USD (USD 0.17216). Example: 9,511 prompt and 1,957 completion tokens must cost exactly USD 0.038592.
6. No cached-token discount or separately priced reasoning tokens, for example `prompt_tokens_details.cached_tokens` absent or 0. Record any such field.
7. Balance after: `GET /api/v1/key` after the call, with no other use of the key in between, gives B1. B0 − B1 equals `usage.cost` exactly. This is what shows that `usage.cost` is Orbio's own charge (UNKNOWN 1.1). Record `X-Orbio-Balance` from the reply too, but do not use it as B1 until its timing and precision are known (UNKNOWN 1.9). If the balance's precision is coarser than `usage.cost`, exact equality cannot be shown, and this item fails.
8. Record the generation `id`. If a cost lookup endpoint exists (UNKNOWN 1.2), its cost for that id equals `usage.cost`.
9. Ledger: the attempt goes RESERVED, then SETTLED at exactly the token charge. Relay `started.json`, gateway `opening` receipts and ledger rows count exactly one request.

If any item fails: the attempt stays UNKNOWN with full liability. There is no second request and no retry. Stop the operator, keep the evidence, and reconcile from the balance read. Orbio is not settled-eligible until the failing item is understood.
