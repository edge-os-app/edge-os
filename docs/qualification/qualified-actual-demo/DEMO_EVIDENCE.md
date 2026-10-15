# Qualified actual demo: judge checklist and sponsor claims (PROPOSED)

Task `QUALIFIED-DATA-PACKET-L4-20261015-LOCAL-v1`. Base `c34bd3959e51696193c1a031652a62fa67829e28`. Status: **PROPOSED. Every item is `NOT_RUN`.** This file grants no operation. It tells the final demo which claim it may make and which saved evidence proves it. Status words are in [QUALIFICATION_GAPS.md section 1](QUALIFICATION_GAPS.md#1-status-words).

## 1. Final judge and demo checklist

Run the steps in order on the exact release build. Each step has one pass condition. A failed step does not stop the checklist; it changes what the demo may claim (section 2). Record the result of every step, including failures, in the release evidence.

| # | Step | Pass condition | If it fails |
|---|---|---|---|
| 1 | Open the build's source list as owner A | One `ACTUAL` release; its SHA-256 equals the approved value and the worker's logged value | Stop the actual-data part of the demo. Show nothing as actual |
| 2 | Open the saved source-fact evidence index | Every declared fact in [OPERATING_PACKET.md section 2.1](OPERATING_PACKET.md#21-history-part) points to a saved, hashed source-fact output | Show the weaker declared value and its reason |
| 3 | Open the saved history dataset | Status `COMPLETE`; window `[T0, T0 + 1,200 s)`; page digests shown; 4 buckets | Show the saved status and gaps as they are |
| 4 | Open the P07 verdict | All five claims `QUALIFIED`, overall `QUALIFIED` | Show the actual verdict and every reason. Skip step 7 |
| 5 | Open corroboration | `COMPLETE`, sample = population, 0 mismatches, chain id 143 | Show the class and counts |
| 6 | Open bucket availability | Each bucket shows `OBSERVED_DELIVERY` and an `available_at` time | Show `ASSUMED_DELAY` or `UNKNOWN` as saved |
| 7 | Open the saved replay | Only after step 4 passed: fills labelled `simulated fills`; run window inside the dataset | Open the saved `DATASET_COVERAGE_UNPROVEN` refusal instead |
| 8 | Open the Nansen report | Saved report; "Powered by Nansen" or "Data provided by Nansen" shown; holders labelled as a collection-time snapshot; credits `KNOWN` 6 or `UNKNOWN` liability shown | Show the saved refusal or failure code |
| 9 | Restart the API and the worker, then reopen steps 3 to 8 | Byte-identical rows and hashes; provider-side counts unchanged | Report the difference; claim no persistence |
| 10 | Sign in as owner B and open each result id | 404 for every one | Stop. Report an isolation defect |
| 11 | Sign out and open each result id | No result readable | Stop. Report a session defect |
| 12 | Open the reconciliation record | reserved = consumed + released + unknown for requests, compute and credits; provider-side counts equal saved client counts | Show the unreconciled values |
| 13 | Open the secret-scan record | 0 key and authorization-header matches in replies, browser results, logs, rows and evidence | Stop. Treat it as a credential incident |

Step 8 shows Nansen data to judges. Do it only after decision D9 in [OPERATING_PACKET.md section 9](OPERATING_PACKET.md#9-decisions-the-builder-makes-once-facts-exist). The Nansen API terms limit use to internal business purposes and require written consent for redistribution.

## 2. Sponsor claim-to-proof map

A claim may be made only when its proof exists and was saved. "Allowed wording" is the strongest wording each proof supports. Anything stronger is not allowed.

| Sponsor or source | Claim | Required proof | Allowed wording when proved | Status |
|---|---|---|---|---|
| Monad | The dataset is actual Monad mainnet history | Checklist steps 1, 3 and 5: `eth_chainId` 143 saved in the run | "Actual Monad mainnet swap history for one pool and one 20-minute window" | `NOT_RUN` |
| Monad | The window's blocks were final when collected | Source-fact P4 finalized read ≥ last scanned block + 2 | "Blocks were finalized before collection" | `NOT_RUN` |
| Envio HyperSync | The application collected the history through HyperSync | Saved page digests, request and reply SHA-256, endpoint host `monad.hypersync.xyz` | "History pages collected with Envio HyperSync" | `NOT_RUN` |
| Envio HyperSync | Delivery times were observed | Source-fact P3 delivery records and decision D3 | "Each bucket's first delivery was observed by a recorder" | `NOT_RUN` |
| QuickNode | Every record was corroborated | Step 5 `COMPLETE` | "Every swap matched a QuickNode receipt" | `NOT_RUN` |
| QuickNode | Units and pool identity were read | Source-fact P1, P2 and P4 outputs | "Token decimals and pool tokens read at the window start and end" | `NOT_RUN` |
| P07 qualifier | The dataset is qualified | Step 4 `QUALIFIED` | "Qualified under the project's P07 rules for this window only" | `NOT_RUN`; `LIMITED` if MOE mechanics stay open |
| Replay | A hypothetical replay ran on actual history | Step 7 pass | "Hypothetical replay with simulated fills; no statistical support; not a trading result" | `NOT_RUN`; refused unless `QUALIFIED` |
| Nansen | The application saved a Nansen report for MOE | Step 8 pass, request ids or request hashes, credits | "Holder snapshot and holder flows from Nansen, powered by Nansen" | `NOT_RUN`; display depends on D9 |
| Nansen | Nansen covers MOE on Monad | An actual reply with MOE data | "Nansen returned MOE data on Monad on <date>" | `NEEDS_FACT` |
| Hermes model | Model research ran through the application | Relay packet proofs | Defined by the relay packet | `NOT_RUN`, separate lane |
| Privy | Login and signer controls | Real login matrix and signer proofs | Defined by those packets | `NOT_RUN`. One uncertain policy POST and one stopped 403 are recorded |
| Kuru | A controlled action on a qualified route | Actual receipt on a qualified route | Defined by that packet | `NOT_RUN`. Current router source `NOT_REPRODUCIBLE` |
| Any | Trading edge, profit, prize readiness or full #58 closure | None | Not claimed | Not claimed |

## 3. Claims that stay forbidden

- "Qualified" for any dataset whose saved verdict is not `QUALIFIED`.
- "Replay of actual history" when the replay was refused.
- "Real-time", "live trading" or "historically attainable execution". The replay uses saved data and simulated fills.
- Any provider or sponsor statement that the provider did not publish or that this run did not save.
- Showing Nansen data publicly before decision D9.
