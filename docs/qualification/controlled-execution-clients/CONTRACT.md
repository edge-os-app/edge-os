# Bounded execution clients

Stage LOCAL, Phase A of CONTROLLED-EXECUTION-CLIENTS-L1-20261018, issues #58, #19 and #20. These modules are unmounted. All executed checks use synthetic data. No actual operating release is approved.

## Public interfaces

| Module | Interface | Boundary |
| --- | --- | --- |
| `execution/kuru_quote_client.py` | `KuruQuoteClient.quote(request)` | One exact accepted ERC-20 request, one HTTP attempt, documented K2 parsing. |
| `execution/transaction_rpc_client.py` | `TransactionRpcClient.call(method, params)` | A finite ordered request plan and explicit broadcast or observer role. |
| `execution/provider_observations.py` | `RpcHoldingsObserver.read`, `observe_monad_charge`, deposit and removal `observe` ports | Existing holdings shape, signed-envelope gas binding, unavailable unsupported provider metadata. |
| `execution/operating_release.py` | `OperatingRelease`, `release_sha256`, `check_release` | Owned canonical bytes, exact authority hash and pure admission before any future credential loader. |

There are no production imports, constructors, settings, exports, routes or registry entries for this bundle. Existing signer, route decoder, signed-byte validator, original-action journal and holdings reader remain unchanged.

## Quote request and response

The accepted caller shape is exactly `chain_id`, `sell_token`, `buy_token`, canonical decimal `amount` and `user`. The client supports documented mainnet chain 143 and nonzero ERC-20 addresses. The frozen wire uses `POST /api/quote` with `userAddress`, `tokenIn`, `tokenOut`, `amount` and an explicit `slippageTolerance`. The caller supplies the existing Bearer token. No token acquisition or refresh exists.

The accepted K2 response has `type`, successful `status`, decimal `output` and `minOut`, `transaction {to, calldata, value}` and all five documented gas-price strings. Input is ERC-20, so transaction value is zero. Calldata is unprefixed even-length hex. Duplicate JSON fields, unknown fields, invalid units, conflicting shapes and unsupported responses refuse. The existing parser checks the accepted shape. The future caller must still decode and compare every route byte and authority field.

`QuoteAvailability` records request identity, local request and receive times, explicit evidence class and unknown provider creation time. Local receive time does not establish provider quote creation or an age of zero. No evidence class comes from a transport class name.

K3 `path` and `buildResponse` remain unsupported. Their inner schema needs a separately reviewed official definition or sanitized actual response. K2 success is synthetic wire proof, not actual schema availability.

## RPC requests and uncertainty

Each client names one role, destination identity, endpoint, exact finite call plan, absolute monotonic deadline and byte bounds. Request IDs start at 1 within the plan. Caller mutation cannot change frozen parameters. Unmatched calls make no request. A consumed slot cannot retry. Broadcast allows only the pending nonce read and one original `eth_sendRawTransaction`. Observer allows the existing chain, finalized block, receipt, native balance and ERC-20 decimals or balance reads. It rejects signing, wallet administration and broadcasts.

A broadcast plan may freeze raw bytes up front. Alternatively its single send slot has `params=None` and a trusted `original_bytes` callback. That callback returns the already journaled original signed bytes after the nonce/sign/validate/save sequence. Construction calls no callback. The slot is consumed before lookup, compares the supplied bytes exactly and freezes the actual wire before one request. The callback is an application-owned in-memory lookup, not a credential reader or provider proxy. Phase B must bind it to the saved attempt and journal. This preserves the unchanged `RpcClient.call` signature without predicting future signatures at construction.

The RPC envelope must contain exactly version, integer request ID and result. Error replies, wrong IDs, invalid quantities, malformed JSON, duplicates, framing mismatches, encoding, redirects, payment, access, rate-limit and server replies remain `RpcError` or `ReplyLost`. Neither proves definitely unsent after possible dispatch. Broadcast success must name the Keccak hash of the frozen raw serialization. Provider text and exception chains do not enter errors. There are no retries, alternate endpoints, fee changes or replacement transactions.

RPC block and receipt inputs use a bounded supported JSON-RPC shape. Unsupported fields or missing required fields refuse. Only the fields used by observers survive projection. Distinct client objects do not establish actual endpoint independence.

The existing standard-library HTTP transport retains its documented resolver and initial-connect containment limit. New clients use its existing absolute deadline contract and check cancellation and time before and after transport and parsing. Injected callbacks must return control for these checks to run.

## Observations

Holdings reuse `read_rpc_holdings` with a frozen wallet, network, assets, decimals and source. Partial, stale, future, wrong-chain or wrong-decimal results refuse. Missing balances never become zero. Current finality qualification is synthetic only. Actual finality and endpoint support remain unavailable.

Monad's documented charge is signed gas limit times `min(base price + signed priority price, signed maximum price)`. `observe_monad_charge` validates signed bytes with the unchanged validator, matches the transaction, wallet, chain, target, receipt block hash, canonical block and finalized boundary, and checks the actual price. The literal test uses limit 200000, gas used 100000 and price 7, with charge 1400000. Missing limits or contradictory price/cap evidence remain unavailable. This is a synthetic observer result, not mounted ACTUAL receipt settlement.

The old `read_original_receipt` still uses `gasUsed * effectiveGasPrice` and receipt presence. Phase B must replace that actual caller calculation and qualify finality. Phase A does not expose that old calculation as actual settlement.

`UnqualifiedDepositObserver` refuses with `DEPOSIT_ORIGINAL_REFERENCE_SCHEMA_UNQUALIFIED`. A balance increase cannot identify a deposit's declared reference or effect. `UnqualifiedRemovalObserver` refuses with `REMOVAL_OWNER_WALLET_SIGNER_SCHEMA_UNQUALIFIED`. No local flag proves provider removal. Neither adapter performs administration.

## Immutable authority and actual refusal

The release owns canonical bytes and returns fresh content copies. Its hash covers network, wallet and signer, policy owner and content, independent proof identity, deployed source/router/ABI identities, route assets and decimals, input/minimum/program/fees/allowance, gas budgets, request/action/attempt/byte/time bounds, expiry, role destinations, finality and every P21 control's state and evidence.

Only `CONTROLLED_ONE_ACTION_QUALIFICATION` is represented. This release establishes no autonomous exit, position-inventory, valuation or cost qualification. Unknown values and all 12 unresolved controls keep admission closed. Nested mutation, type coercion, bool-as-number, placeholder identity, role drift, content drift, missing proof, unsupported schema or expiry cannot produce approval.

`APPROVED_ACTUAL_RELEASES` is an empty immutable server-owned mapping. `check_release` rejects ACTUAL releases, including requests carrying their own matching hash or a test approval. No environment loader, file loader, application endpoint or actual constructor override can register approval. Synthetic tests supply an explicit test-owned map for `SYNTHETIC_FIXTURE` authority on `.invalid` endpoints. That seam is never mounted.

## Verification and retained limits

Four owned test files exercise the public interfaces with literal synthetic responses, transport doubles, clock injection and no-network sentinels. The complete recipe runs them with the unchanged signed-byte and Kuru tests. A second serial command runs `test_privy_signer.py -k 'not loopback'`. No socket, service, database or browser check is included. Both original independent reviews and the separate gate bind one exact committed candidate.

Phase B remains a separate successor after accepted Phase A and L3 wallet integration, shared-path release and a fresh base. It owns application composition, per-attempt signer construction, saved job and authority propagation, fresh market inputs, corrected actual receipt settlement, recovery, owner revocation and the mounted database/API/browser journey.

Actual Privy enforcement and metadata schema, supported access, exact Kuru schema, deployed identities, finality support, account limits, financial terms and independent proof remain unqualified. The historical uncertain policy POST and stopped Cloudflare 403 stay unresolved. No retry or bypass follows from this bundle. All 12 P21 controls and the separate position-inventory restriction remain required.

## Sources

Current official reads on 2026-10-18 used Context7 first. No matching Kuru library was found. The [Monad Kuru guide](https://docs.monad.xyz/guides/kuru-flow) supplies the K2 wire fields. [Monad gas pricing](https://docs.monad.xyz/developer-essentials/gas-pricing) supplies the gas-limit charge. The [Monad JSON-RPC reference](https://docs.monad.xyz/reference/json-rpc/api) supplies protocol method context. These are documented semantics, not observed provider behavior.

Accepted local sources remain [Kuru adapter profile](../../implementation/KURU_FLOW_ADAPTER_PROFILE.md), [mandatory restrictions](../route-restrictions/CONTROL_RESTRICTIONS.md), [policy binding feasibility](../route-restrictions/PRIVY_POLICY_BINDING_FEASIBILITY.md), [signer contract](../privy-signer-http/README.md), [deployed identity findings](../kuru-deployed-source/README.md), [unfunded proof contract](../privy-unfunded-proof/CONTRACT.md) and [actual original-action prerequisites](../original-transaction/ACTUAL_ORIGINAL_TRANSACTION_QUALIFICATION_PACKET.md).
