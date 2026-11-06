# Orbio release: one record and one price table (values approved, no paid call authorized)

Task `CLOUD-ORBIO-RELEASE`, builder-approved normal cloud session, 2026-10-22, base `617b9e2add99305b3da1a94f80b8ca7ca1924c9d` (CLOUD-02, relay contract A8). Updated by `CLOUD-ORBIO-01`, builder-approved normal cloud session, 2026-10-30, on branch `cloud/orbio-01-route`. Finished by `ORBIO-ROUTE-L4-20261105`, 2026-11-05, base `47b8906a7897a49d486b5b6692e8df7b5cb3c77e`. Status: RELEASE VALUES APPROVED AND REGISTERED. The paid call still needs a funded key and the builder's approval.

`orbio-first-call-1` is approved beside `hermes-first-call-1`. Each has its own record, price, destination and CA bundle.

- Its record SHA256 `041f588d3b9564fd605d00d2204083cbfc4e4cd3307906656345a73118ac563f` is in `relay_admission.APPROVED_ACTUAL_RELEASES`, and `hermes_relay_composition.RELEASE_DEFINITIONS` holds its definition.
- Only an operator handoff selects a release, by record hash. There is no default: no handoff means no start. Nothing in the settings, the deployment files or the scripts names Orbio.
- No key was read and no HTTP request was sent to Orbio's API. The only contact was the controller's public catalogue read and the handshake-only TLS check of 2026-11-05 (section 1.4). Nothing was bought.

The OpenRouter record, approval packet, price snapshot, definition and CLOUD-02 golden bytes are unchanged.

## 1. Source facts (public Orbio documentation)

Sources, all on Orbio's own domain `orbio.so`:

- <https://www.orbio.so> (home page and pricing)
- <https://www.orbio.so/developers> (API documentation)
- <https://www.orbio.so/llms.txt> (agent guide)
- <https://www.orbio.so/api/v1/models> (public model list and prices; no key)

Look-alike sites `orbioagent.world` and `orbio-proposals.xyz` are not Orbio and are not sources.

### 1.1 How these facts were obtained

- 2026-10-22: the builder read Orbio's public documentation and gave the facts in the first table below. The CLOUD-ORBIO-RELEASE session did not fetch them.
- 2026-10-30 (CLOUD-ORBIO-01): the builder read the four pages above and gave the pricing facts in the second table in the ticket. This session tried to read the same four URLs at 2026-10-30 09:47 UTC. `curl` through the session proxy got `CONNECT tunnel failed, response 403` for all four. The fetch tool got `getaddrinfo ENOTFOUND www.orbio.so`, which means the host is outside this session's allowed network domains. No byte was received from Orbio. A web search restricted to `orbio.so` returned only model-written summaries of cached pages, and those summaries disagree with each other (one gives a top discount of 50%, another 55%). They are not used as sources.
- So every 2026-10-30 fact below is **given by the builder, read 2026-10-30, not verified by this session**. Nothing from `/api/v1/models` was read. The pinned model's catalogue entry is UNKNOWN U6.

The builder decisions and controller readings of 2026-11-05 are in section 1.4. They replace the "not read" statements above for U5, U6 and U8.

### 1.2 Facts given 2026-10-22

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

### 1.3 Pricing facts given 2026-10-30 (from <https://www.orbio.so>, read 2026-10-30)

| Fact | Status |
|---|---|
| Pricing is a "Liquidity Book": credits are sold in discount tiers from 0% to 50% off; the top tier is about 47.5% | given by the builder, read 2026-10-30 |
| A 5% platform fee is charged on the discounted price | given by the builder, read 2026-10-30 |
| Minimum purchase USD 5 | given by the builder, read 2026-10-30 |
| "Requests use Orbio's managed OpenRouter account" | given by the builder, read 2026-10-30 (quoted) |
| The model list and prices are public at <https://www.orbio.so/api/v1/models>, with no key | given by the builder; not read by this session |

### 1.4 Decisions and readings of 2026-11-05

| Item | Result | Source |
|---|---|---|
| Terms of service and privacy policy | accepted | builder, step 1 |
| Catalogue entry for `openai/gpt-6.1-sol` | listed; prompt 0.000002 and completion 0.00001 USD per token; one override, at `min_prompt_tokens` 272000 (prompt 0.000004, completion 0.000015); no time-of-day part | controller read <https://www.orbio.so/api/v1/models>, 2026-11-05 |
| Override reach | the 65,536-byte request limit cannot reach 272,000 prompt tokens | section 4 rule 3 |
| Routing | option (b): a reviewed code change admits a release that names no routing | builder, step 3 |
| TLS | `api.orbio.so:443`, SNI `api.orbio.so`, against `orbio_ca_isrg_root_x1.pem` alone: TLSv1.3, verify return code 0, chain api.orbio.so, YR1, Root YR, ISRG Root X1 | controller, handshake only, step 4 |
| Reply headers | option one: the relay records `X-Orbio-Ignored-Parameters` and `X-Orbio-Balance` | builder, step 5 |
| Credit purchase | card top-up from USD 5; the key is the account key `sk-orbio-...`; the builder buys later, outside this ticket | builder, step 6 |

Worst case for a buyer. A buyer at the 0% tier pays the list price plus 5% of it: 1.05 × list. Any discount lowers the cash paid, so 1.05 × list is the most a buyer can pay per token, as long as the list rate itself is right. The section 4 snapshot uses it.

Is the cost returned in usage data? **UNKNOWN until the paid call.** No public Orbio page that the 2026-10-22 or 2026-10-30 readings covered documents a `usage.cost` field, a cost header or a cost lookup endpoint. Those sessions could not read <https://www.orbio.so/developers> or <https://www.orbio.so/llms.txt>, so this does not claim the field is absent either.

Status of U1 to U11. An UNKNOWN is not documented, not tested and not assumed below:

- U1. UNKNOWN until the paid call. Whether replies include `usage.cost` in their usage data, and what it means: Orbio's charge (discounted, with the fee), OpenRouter's upstream charge at list price, or something else.
- U2. UNKNOWN until the paid call. Whether a cost lookup endpoint exists, like OpenRouter's `GET /api/v1/generation?id=`.
- U3. UNKNOWN until the paid call. Whether OpenRouter's `provider` routing object is forwarded, dropped or rejected. This release sends none, so the call does not depend on the answer.
- U4. UNKNOWN until the paid call. The exact reply `model` field and any provider fields in the reply.
- U5. CLOSED 2026-11-05. The builder accepted Orbio's terms of service and privacy policy.
- U6. CLOSED 2026-11-05. `openai/gpt-6.1-sol` is listed at USD 2 / 10 per million, with one override at 272,000 prompt tokens that this release cannot reach (section 1.4, section 4 rule 3).
- U7. UNKNOWN until the paid call. Whether `reasoning`, `response_format`, `max_tokens` and `prompt_cache_options` are forwarded or dropped. Only "sampling parameters" are documented as dropped.
- U8. CLOSED 2026-11-05. The handshake verified to ISRG Root X1 with this bundle alone (section 1.4).
- U9. UNKNOWN until the paid call. Whether the `X-Orbio-Balance` value on a reply is read before or after that reply's charge, and its precision.
- U10. UNKNOWN until the paid call. Whether the Liquidity Book discount and the 5% platform fee apply only when credits are bought, so that each request then draws list-price face value from the balance, or whether they change what each request is charged. Either way the cash paid per token is at most 1.05 × list.
- U11. UNKNOWN until the paid call. Whether the balance is denominated in USD cash or in inference face value.

## 2. The record

Files in this folder:

| File | SHA256 | Meaning |
|---|---|---|
| `orbio_first_call_record.json` | `041f588d3b9564fd605d00d2204083cbfc4e4cd3307906656345a73118ac563f` | the ACTUAL record, canonical JSON in the CLOUD-02 shape |
| `orbio_first_call_approval.json` | `22e9ccdc52de423f8c612bc59376bec38357a47134f2c130b50a75e7c9e23e48` | status `APPROVED_RELEASE_VALUES`; the record's `approval` names it. The record values, decisions, readings and open facts. It authorizes no call, key or purchase |
| `orbio_first_call_prices.json` | `4f83b00bd51b0614f1da551c762ce8969f27c5bb26bf5edf8a3f6e3412f982dc` | the price snapshot |
| `orbio_ca_isrg_root_x1.pem` | `22b557a27055b33606b6559f37703928d3e4ad79f110b407d04986e1843543d1` | the CA bundle: ISRG Root X1 only |

The record is the adopted OpenRouter record (`hermes-first-call-1`) with these differences only:

| Field | OpenRouter (approved) | Orbio (approved) | Why |
|---|---|---|---|
| `release_id` | `hermes-first-call-1` | `orbio-first-call-1` | |
| `route_id` | `openrouter-openai-standard` | `orbio-openrouter-managed` | |
| `destination` | `openrouter.ai`, 443, `/api/v1/chat/completions` | `api.orbio.so`, 443, `/api/v1/chat/completions` | the documented API host. `www.orbio.so` is not used: a release has one host, and the gateway admits only that host |
| SNI and verified name | `openrouter.ai` | `api.orbio.so` | A8: the TLS server name is the record's host. The record has no separate SNI field |
| `provider` (routing) | `only: [openai]`, no fallbacks, required parameters, `data_collection: deny`, `max_price` 2/10 | `null` (no routing fields) | forwarding of the routing object is UNKNOWN U3. Naming it would claim a provider pin, a privacy setting and a price ceiling that nothing shows Orbio applies |
| `allowed_fields` | includes `provider` | no `provider` | follows from no routing |
| `ca_bundle_sha256` | `7cef540c…` (OpenRouter's bundle) | `22b557a2…` (the ISRG Root X1 PEM above) | pin the root only |
| `price_snapshot_sha256` | `e53259b2…` | `4f83b00b…` | snapshot names seller `orbio` at the worst-case rates USD 2.1 / 10.5 (section 4) |
| `approval` | the adopted packet | the Orbio packet | |
| `recorded_reply_headers` | absent | `X-Orbio-Balance`, `X-Orbio-Ignored-Parameters` | step 5 option one; a record may name exactly these two or omit the field |

Unchanged: `kind` ACTUAL, `stream` false, `model` `openai/gpt-6.1-sol`, `max_tokens` 4096, `reasoning` `{"effort": "low"}`, `response_format_sha256` `cdffe6fd…`, `prompt_cache_options` `{"mode": "explicit"}`, `max_request_bytes` 65,536, `max_reply_bytes` 262,144, `timeout_seconds` 90.

CA pin. The bundle holds one certificate, ISRG Root X1. Its DER SHA256 fingerprint is `96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6`, which is Let's Encrypt's published value; the test checks it. The relay builds `ssl.create_default_context(cafile=<bundle>)` with no system store. So verification succeeds only if the server sends leaf → YR1 → ISRG Root YR (cross-signed by X1). No intermediate is pinned, and ISRG Root YR is not added as a trust anchor. The controller's handshake of 2026-11-05 showed that chain (U8 closed).

## 3. What the code does with this record

Checked by `tests/hermes_provider_relay/test_orbio_first_call_release.py`, `test_release_without_routing.py`, `test_relay_reply_headers.py` and `apps/api/tests/test_hermes_unrouted_release.py`, `test_hermes_release_selection.py`, `test_provider_spend_routes.py`:

1. With the default registry, `load_actual_release(raw, sha)` loads the record, with its own destination, CA pin and no routing.
2. A record may name no routing (`provider` null). A routed record keeps every earlier check. For a record with no routing:
   - the loader requires that `allowed_fields` has no `provider`;
   - the request body must not carry `provider`, and its required fields are the routed set without it;
   - `bind_release` requires the definition to name a seller exactly when the record names no routing, and the snapshot `provider` to equal that seller;
   - the snapshot rates have no `max_price` cap, because no routing object names one. They must still be plain positive rates;
   - `LiveRelease.provider` is the seller.
3. The relay saves only the two named headers, on `finished.json`, as `reply_headers`. It does not save a value over 256 characters, a value with a character that is not printable ASCII, or a value that holds the key or the `sk-orbio-` prefix. For such a value it saves only the reason, in `reply_headers_refused`. A record that names no headers saves neither field, so OpenRouter evidence is unchanged.
4. The snapshot is the worst case a buyer pays (section 4): each rate is 1.05 × the adopted OpenRouter rate, and the worst-case reservation is 180,768,000 nano-USD.
5. The operator handoff selects the release. An unknown hash, an unapproved hash, a definition in one registry only, or handoff bytes that do not match the given SHA256 are refused before any launch. An existing OpenRouter configuration selects the same OpenRouter release.
6. One ledger database serves every route. Caps stay in the one settings row, so the cap check sees OpenRouter and Orbio spend together. Each reservation saves its `route_id`. Each route's token price is frozen at that route's first use, and a later different price gets the same refusal. Settlement uses the price of the reservation's own route.
7. The adopted record, approval packet and price bytes keep their SHA256 values. The CLOUD-02 golden test (`test_release_destination_golden.py`) still passes unchanged.
8. The relay checks the key file at start, before it serves anything. A release that sends to `api.orbio.so` takes only a key that starts with `sk-orbio-`, and every other ACTUAL release refuses such a key. A key that an HTTP header cannot carry unchanged is refused too. A refusal ends the relay, so no handoff, grant, `started.json`, byte or spend can follow. The record holds a fixed reason and no part of the key. The operator still never opens the file.

## 4. Price table rule

The price snapshot (CLOUD-ORBIO-01) is:

```json
{"completion_usd_per_million":"10.5","model":"openai/gpt-6.1-sol","prompt_usd_per_million":"2.1","provider":"orbio"}
```

Why these rates. The snapshot is the worst case the buyer can pay for the pinned model, so the reservation is never below the real charge:

- list rate: USD 2 prompt, USD 10 completion per million. This is the rate read from <https://www.orbio.so/api/v1/models> on 2026-11-05 (section 1.4), and it equals OpenRouter's rate for `openai/gpt-6.1-sol`;
- no Liquidity Book discount: the 0% tier. A buyer who gets any discount pays less (1.3);
- plus the 5% platform fee on the discounted price, which is the list price at the 0% tier (1.3);
- so 1.05 × list: USD 2.1 prompt, USD 10.5 completion per million.

The 2026-10-22 draft used USD 2 / 10, the list rate with no fee. That is below what a 0%-tier buyer pays, so it was raised.

Rule. An Orbio snapshot may be adopted only with rates at or above the worst case, and only when all of these hold:

1. Orbio's public catalogue <https://www.orbio.so/api/v1/models>, read on the approval date from `orbio.so` itself, lists `openai/gpt-6.1-sol`.
2. Its list prompt and completion rates are USD 2 and USD 10 per million (the same as OpenRouter's public price on that date). If they are higher, the snapshot becomes 1.05 × the listed rates, and the record is re-hashed.
3. The model has no time-of-day override and no cache, reasoning, request or other fee. A token-count override is allowed only when the record's own `max_request_bytes` plus the input token margin cannot reach it.

Rule 3 was amended on 2026-11-05 under Decision 2 of `ORBIO-ROUTE-L4-20261105`. It first refused any token-count override. The catalogue reading showed one override only, at `min_prompt_tokens` 272000, with no time-of-day part. The request limit gives at most 65,600 prompt tokens, so that rate cannot apply.

4. The platform fee is still 5% of the discounted price, and no tier costs more than the list price.

The reading of 2026-11-05 covers rules 1 and 2 and the override part of rule 3, as amended. It records nothing on the other fees in rule 3 or on rule 4. Section 8 re-checks those before the call. If any rule fails, no Orbio release is approved for that model. In particular, no rate is averaged, no discount tier is assumed, and no rate is picked as "the usual one" for an override model.

`provider` names the seller, `orbio`, because the upstream endpoint is not pinned. The ledger's two-rate `TokenPrice(2.1, 10.5)` is the same object for reservation, settlement and the relay cost check (E1-COST1). The worst-case reservation is (65,600 × 2.1 + 4,096 × 10.5) / 1,000,000 = USD 0.180768 per request (180,768,000 nano-USD), above OpenRouter's USD 0.17216. 65,600 is `max_request_bytes` 65,536 plus the input token margin of 64.

Minimum purchase. Orbio's minimum purchase is USD 5 (1.3). That is above the shared USD 2.00 model and data ceiling. Buying credits is a separate financial decision (section 7 step 6). The ledger ceiling still bounds what the application may spend, but the purchase itself exceeds it.

## 5. Settlement question

The application settles a counted reply only when (`relay_turn_runner._cost_equals_charge`, E1-COST1):

`ceil(usage.cost × 10^9)` nano-USD == `TokenPrice.nano_usd(prompt_tokens, completion_tokens)` = `prompt_tokens × 2,100 + completion_tokens × 10,500` nano-USD, and that charge is at most the held reservation.

The relay also requires these for a counted reply (`ActualRelease.reply_check`):

- status 2xx and `application/json`, with no content encoding;
- exactly one choice, with `finish_reason` `stop`;
- reply `model` exactly `openai/gpt-6.1-sol`;
- integer `prompt_tokens`, `completion_tokens` and `total_tokens`;
- a finite, non-negative numeric `usage.cost`.

Otherwise the attempt is UNKNOWN. The text is withheld, nothing is resent, and the full USD 0.180768 stays as liability.

The open question is whether Orbio's `usage.cost` exists in its usage data (UNKNOWN U1) and equals the buyer's own token-priced charge for this request. Because the snapshot is the worst case, a `usage.cost` at OpenRouter's list rate (2 / 10), or at a discounted rate, does not equal the snapshot charge. The attempt then stays UNKNOWN with full liability: the ledger over-reserves and never settles low. Settling exactly at a discount tier would need a snapshot for that tier, which is a separate builder decision that must still keep the reservation at or above the real charge. If `usage.cost` is OpenRouter's upstream cost, Orbio's markup or another figure, then equality with the token charge is a coincidence, not a settlement. One counted reply proves only one request.

## 6. Variable-price risk

- Discount and fee. The snapshot is the 0%-tier price plus the 5% fee. If Orbio raised the fee, or priced a tier above list, the real charge could exceed the reservation. Section 4 rule 4 is re-checked on the approval date.
- Override models. 78 models carry token-count or UTC time-of-day overrides. `openai/gpt-6.1-sol` had one on 2026-11-05, out of this release's reach (section 4 rule 3). If it gains another after approval, the two-rate price is wrong at some times or sizes. A higher rate can make the real charge exceed the reservation. The ledger's liability then understates real spending against the shared USD 2.00 ceiling, which the relay cost check cannot see before the request is sent.
- No price ceiling on the wire. OpenRouter's `max_price` routing limit is what makes the provider refuse a pricier endpoint. With no forwarded routing object, nothing on the request bounds the price. Only the catalogue reading and the after-the-fact cost check remain.
- No provider pin. Without `only` and `allow_fallbacks: false`, Orbio's OpenRouter account may route to any endpoint for the model, at that endpoint's price and data policy. `data_collection: deny` is not applied.
- Catalogue drift. "Identical to OpenRouter" is a documented claim as of 2026-10-22, not a contract. Either side can change prices between the catalogue reading and the call.
- Failure mode. Every mismatch above makes the attempt UNKNOWN with full liability, so the ledger never settles low by mistake. The risk is a charge above the reservation, and a ceiling that can only be reconciled from the Orbio balance.

## 7. Approval steps and status

Step 1: DONE 2026-11-05. The builder read Orbio's terms of service and privacy policy and accepted them (U5 closed).

Step 2: DONE 2026-11-05. The controller read the public catalogue. The rate is the list rate, and the override cannot apply under rule 3 as amended (U6 closed). Section 8 re-checks the other fees and rule 4 before the call.

Step 3: DONE 2026-11-05. The builder chose option (b). A reviewed code change admits a release that names no routing, without relaxing any OpenRouter check. It covers every routing use, including the snapshot `provider` and `max_price` rules (section 3).

Step 4: DONE 2026-11-05. The controller ran the handshake-only TLS check. It verified to ISRG Root X1 (U8 closed).

Step 5: DONE 2026-11-05. The builder chose option one. The relay records the two named headers (section 3 item 3).

Step 6: OPEN. The builder buys credits and creates the account key `sk-orbio-...`. This is a paid purchase that needs explicit financial authorization. The minimum purchase is USD 5, above the shared USD 2.00 model and data ceiling. Any discount tier is at or below the snapshot price.

Step 7: DONE 2026-11-05. The packet holds the final values, date and base, and the packet and record are re-hashed. The record's SHA256 is in `APPROVED_ACTUAL_RELEASES` and its definition is in `RELEASE_DEFINITIONS`, in one reviewed change. The builder accepted several approved releases: Orbio stands beside OpenRouter, and the operator handoff selects one. Selecting Orbio stays an explicit operator choice. Integration into `main` keeps its own authorization.

Step 8: OPEN. The builder authorizes exactly one paid test call under the section 8 checklist.

## 8. Paid-call checklist (one request; nothing here is authorized)

Before the call:

- [ ] Steps 1 to 7 are done and recorded, and the builder authorized step 8.
- [ ] The builder records the balance B0, the usage and the rate limits, from Orbio's account page or from `GET /api/v1/key` in the builder's own terminal. The controller does not do this read, because the relay alone reads the key.
- [ ] Rerun the handshake-only TLS check before the leaf certificate expires on 2026-12-06, from the pinned image's own Python. That image has Python 3.14.8 and OpenSSL 3.5.7; the check of 2026-11-06 used Python 3.14.4 and OpenSSL 3.6.4. The image has the same strict settings, but the handshake has not run on its OpenSSL.
- [ ] Record the call's UTC time, and confirm the catalogue list rates for that model at that time are still USD 2 / 10 with no reachable override, no cache, reasoning, request or other fee is listed, the platform fee is still 5%, and no tier costs more than the list price (section 4 rules 3 and 4).

Operator steps. The controller runs these. The key stays in one file that only the relay reads. The operator only checks that file's mode and place, and never opens it.

Use the API's Python in every command, as the commands show. A plain `python` is not on the path. Set `PYTHONPATH` to this checkout's `apps/api/src` in steps 3 to 7 and 11: the virtual environment's editable install can name another checkout, and steps 5 to 7 would then run that checkout's code.

1. The builder writes the key to a file outside the repository, with mode 0600, and gives the controller its path only. The file holds one line. The relay checks the key at start: this release takes only a key that starts with `sk-orbio-`.
2. Write the operator configuration (`docs/qualification/hermes-actual-operation/README.md` section 3) with these values:
   - `kind` `ACTUAL`, `release` null, `shutdown_owner` `relay_operator`;
   - `release_record`: the absolute path of `orbio_first_call_record.json`, with the SHA256 in section 2;
   - `ca_bundle`: the absolute path of `orbio_ca_isrg_root_x1.pem`, with the SHA256 in section 2;
   - `image`: `id` is the pinned image id for this host from `RELEASE_DEFINITIONS`, and `reference` is the local tag of that image (`docker images --no-trunc` shows it). The operator launches by the id and refuses a tag with another id;
   - `channel` name `edge-os-research`; a new `run_root` and channel folder, each in a folder that exists;
   - `provider_key_file`: the path from step 1.
3. From the repository root, run `apps/api/.venv/bin/python scripts/hermes_provider_relay/relay_operator.py CONFIG check`, then the same command with `start`. Keep the printed handoff path and SHA256. If `start` prints `refused: the relay refused the provider key file`, the key is the wrong one for this release. The reason is in `<run root>/relay/state/provider-key-refused.json`, and no handoff exists, so nothing can be sent. The builder corrects the file; use a new `run_root` and channel folder.
4. Set the application's environment. `EDGE_OS_ENV` is `local`, `EDGE_OS_INTERPRETER` is `hermes_local`, and `EDGE_OS_CORS_ALLOWED_ORIGINS` names the web page's origin. `EDGE_OS_DATABASE_URL`, `EDGE_OS_PRIVY_APP_ID` and `EDGE_OS_PRIVY_VERIFICATION_KEY` come from the recorded local env files. The Privy values are the same ones the web page signs in with.
5. From `apps/api`, run `.venv/bin/python -m alembic upgrade head`, then `.venv/bin/python -m alembic check`. The application refuses a database below migration 0015.
6. From `apps/api`, run `.venv/bin/python ../../scripts/hermes_app_mount/serve_relay_application.py --handoff-path PATH --handoff-sha256 SHA --run-id ID --port PORT`. Confirm that its `serving` line names `orbio-first-call-1`.
7. Start the ordinary API, because the step 6 application serves the six Hermes paths only and the web page also needs `/v1/me`. From `apps/api`, use the step 4 environment with two changes: `EDGE_OS_INTERPRETER` is `fixture`, and `EDGE_OS_HERMES_APP_URL` is `http://127.0.0.1:PORT`, with the step 6 port. Run `.venv/bin/python -m edge_os_api --host 127.0.0.1 --port API_PORT`. This API forwards the six paths to the step 6 application and keeps every other path.
8. Start the web page with `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:API_PORT` and `NEXT_PUBLIC_PRIVY_APP_ID` set to the same value as `EDGE_OS_PRIVY_APP_ID`, and run `npm run dev -- --port WEB_PORT --hostname 127.0.0.1` from `apps/web`. A checkout without `apps/web/node_modules` needs `npm ci` first; a link to another checkout's folder does not work, because the dev server refuses it. A `next build` needs these two values at build time. `http://127.0.0.1:WEB_PORT` must be exactly the origin in `EDGE_OS_CORS_ALLOWED_ORIGINS`. The web origin must be on the Privy app's allowed origins; if it is not, sign-in fails before any request. Open `/app`. The research rows belong to a signed-in owner, and the only sign-in is Privy, so the builder signs in. The controller holds no sign-in token.
9. The builder submits one research request on that page. That request calls `POST /v1/research/requests`, which makes the one provider request. Do not submit a second request, and do not press retry.
10. Read the evidence:
   - the attempt's `finished.json` in `<run root>/relay/state/<attempt>/` (`usage`, `cost`, `generation_id`, `reply_headers`, `reply_headers_refused`);
   - the reply body, `<channel>/turn-NN-<attempt>/output/relay-channel/reply.json`, for `finish_reason`, the reply `model`, provider fields and `prompt_tokens_details`. The file holds the body in `body_b64`, so decode it first;
   - the gateway `opening` line in `<run root>/relay/gateway/receipts/tunnels.jsonl`, and the ledger row in `usage_local.provider_spend_reservations` for the attempt.
11. Stop the web page, the ordinary API and the application. From the repository root, run `apps/api/.venv/bin/python scripts/hermes_provider_relay/relay_operator.py CONFIG stop`, whatever the result. Keep the run root. Before any publication, the builder scans for the key, because only the builder and the relay read that file: `grep -rlF -f KEY_FILE RUN_ROOT CHANNEL_FOLDER` must print nothing.

The caps need no hand check: the one ledger counts both routes (section 3 item 6).

The one call must observe all of these:

1. HTTP 200, `content-type: application/json`, and no `content-encoding`.
2. `X-Orbio-Ignored-Parameters` absent or empty in `finished.json` `reply_headers`. If it names `reasoning`, `response_format`, `max_tokens`, `prompt_cache_options` or any other sent field, the release shape is not honored.
3. One choice with `finish_reason` `stop`, and reply `model` exactly `openai/gpt-6.1-sol`. Record any provider field in the reply (UNKNOWN U4).
4. Integer `usage.prompt_tokens`, `completion_tokens` and `total_tokens`, equal to the job's counts.
5. `usage.cost` present and numeric, with `ceil(cost × 10^9) == prompt_tokens × 2,100 + completion_tokens × 10,500` nano-USD and at most 180,768,000 nano-USD (USD 0.180768). Example: 9,511 prompt and 1,957 completion tokens must cost exactly USD 0.0405216. A cost at a discounted rate or at the list rate does not settle (section 5).
6. No cached-token discount or separately priced reasoning tokens, for example `prompt_tokens_details.cached_tokens` absent or 0. Record any such field.
7. Balance after: the builder repeats the B0 read after the call, with no other use of the key in between, and gives B1. B0 − B1 equals `usage.cost` exactly. This is what shows that `usage.cost` is Orbio's own charge (UNKNOWN U1). Read `X-Orbio-Balance` from `reply_headers` too, but do not use it as B1 until its timing and precision are known (UNKNOWN U9). If the balance's precision is coarser than `usage.cost`, exact equality cannot be shown, and this item fails.
8. Record the generation `id`. If a cost lookup endpoint exists (UNKNOWN U2), its cost for that id equals `usage.cost`.
9. Ledger: the attempt goes RESERVED, then SETTLED at exactly the token charge. Relay `started.json`, gateway `opening` receipts and ledger rows count exactly one request.

If any item fails: the attempt stays UNKNOWN with full liability. There is no second request and no retry. Stop the operator, keep the evidence, and compare the ledger liability with the balance read. Orbio is not settled-eligible until the failing item is understood.
