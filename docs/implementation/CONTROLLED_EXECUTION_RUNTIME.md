# Controlled one-action runtime

Phase B mounts the existing clients into the durable application. Local checks use fake credentials and injected transports. No actual operating release or binding is registered. A mode value grants no authority.

## Composition

`build_financial_services` takes an explicit `api`, `worker` or `recurring` role. The three entry points supply their roles. The API and recurring views remove quote and signer credential loaders from registered runtimes. The API can read holdings and recover a saved original hash through the independent observer. It cannot obtain controlled signing or broadcast clients. The recurring producer has no controlled approval. Existing authored fixture behavior remains separate.

`unavailable` remains the default. `controlled` is a local configuration option with an empty server registry. Production restrictions and the API app-secret prohibition remain. No environment variable, HTTP body or file loader can register an actual approval. The server-owned actual release and binding registries are empty immutable mappings.

## Exact authority

`OperatingRelease` owns the accepted route, deployed identities, P21 controls, wallet/signer/policy, amounts, fees, gas, endpoints, request bounds and expiry. `BoundRelease` adds exact saved owner, agent, wallet address, publication/execution revisions, consent adoption, review and terms identities. Its hash also covers independent inventory, exit-capacity, valuation, cost, market and finality proof references. Current inputs require a frozen source, delivery profile, finalized boundary, warmup size and collection limit.

Controlled consent uses `connected-one-action/1` and permits one ENTRY. `ControlledApproval` carries its release and proof references. Autonomous fixture qualification flags stay false. Missing proof, changed terms, expired authority, wrong identity or an unapproved actual release denies admission before credential acquisition. All twelve P21 controls and inventory requirements remain mandatory.

The existing ledger still reserves entry and intended-exit gas and two attempt slots. This protection does not qualify exit execution. The controlled runtime supplies no EXIT or recurring submission. Receipt accounting preserves attributable inventory and residual exposure.

## Saved attempt and one send

`ExecutionService` remains the owner of the queue, claim, admission transition, attempt and journal. No new table or queue exists. `OriginalTransactionTransport` calls the controlled attempt hook only after it receives the saved attempt. The hook verifies the exact IN_FLIGHT attempt, active claim and submission-owned admission before any credential or provider operation. A prior saved attempt for that exact adopted consent prevents another controlled client attempt, including after a definite refusal.

The Kuru client loads its token only inside that saved-attempt boundary. Preparation uses the released raw minimum exactly. The preliminary action terms identify an APPROVED_MINIMUM, not a provider estimate. The actual quote/build request occurs once during original preparation. Elapsed quote and input ages are checked after the response. Provider quote creation time remains unknown.

The journal saves PREPARED and SIGN_REQUESTED before constructing `PrivySignerClient`. The factory re-reads saved ownership and uses the same attempt ID as the idempotency key. Request expiry comes from the immutable release. Saved consent, revision, wallet, expiry and stops are checked before signing and broadcast.

Signed bytes must match every frozen unsigned field and the verified wallet. SIGNED saves the full bytes and their full Keccak hash. BROADCAST_REQUESTED must then persist. The accepted bounded RPC client reloads and validates those exact saved bytes before its one send. Lost replies never cause another quote, nonce, signature, send or action.

## Read-only evidence and recovery

Current execution inputs use `MarketObservationPort` and `ForwardObservation`. A qualified runtime checks the exact market, slot, source, delivery profile, units, assets, warmup and finalized collection window. Research history, Nansen context and delayed replay cannot become this feed through a label. Missing source/profile or incomplete inputs makes the action unavailable.

Release-bound holdings require the exact owner, wallet, network, assets, decimals and independent finalized observer. Reads stay at the selected block, whose hash remains in the source reference. Unknown deposit-reference and signer-removal schemas remain unavailable. Balance changes and local flags cannot prove those effects.

Recovery checks refusal, in-flight and missing-hash states before acquiring any observer. A saved hash is observed without constructing execution clients or loading worker credentials. Controlled settlement verifies the saved release, full original bytes, chain 143, wallet, target, canonical receipt block and independently qualified finalized boundary. It requires complete supported ERC20 effects and bound, non-removed logs. Transfers of unsupported wallet assets and conflicting log transaction identities also stay UNKNOWN. Missing or conflicting evidence keeps reservations held.

Monad gas uses the signed gas limit multiplied by `min(base fee + signed priority fee, signed maximum fee)`. Receipt gas used is not the charged limit. Saved authored original actions retain their legacy fixture meaning and labels. An unbound controlled envelope cannot fall back to receipt presence.

Controlled public gas amounts and nonces use decimal strings, preserving integers beyond the browser number limit. The consent card shows the raw input, minimum, fees, gas, expiry and exact signer/policy. Action views distinguish actual, synthetic and authored evidence and show current source identity, receipt cost, pending exposure and recovery.

## Required proof and remaining limits

Use the candidate-bound worker evidence for exact commands and results. Focused pure checks do not replace the required owner API, migrated PostgreSQL, persisted job, trusted worker, original journal, independent receipt, reconciliation, restart and UI proofs. Those stages need the controller's fresh serial runtime grant. Both original independent assessments and the separate gate must cover the same final candidate before local integration.

Local acceptance does not qualify a funded demo. Actual use still needs independent control and inventory qualification, exact registered release/binding, supported current sources and provider metadata, verified custody, exact financial terms and separate operation authority. The USD2 trading ceiling includes gas and remains separate from the model/data ceiling. No real provider, wallet, signing, broadcast, funding, publication or deployment operation follows from this implementation.
