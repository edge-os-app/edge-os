# P16 provider signing result

Date: 2026-10-08. Test scope: one authenticated owner, two existing unfunded wallets, Monad Testnet `10143`, zero-value self-calls. No extra wallet or owner was created.

## Result

The six authorized sign-only calls completed in order:

| # | Caller and target | Result |
|---|---|---|
| 1 | A signer signs A's configured self-call | `SIGNED`; 228-byte result discarded |
| 2 | B signer signs B's configured self-call | `SIGNED`; 228-byte result discarded |
| 3 | A signer attempts B's configured call against B | Raw result `DENIED_UNCLASSIFIED`, HTTP 401, no code. The separate local control classifier records `CONTROLLED_PROVIDER_REFUSAL`. |
| 4 | Owner signs A's configured self-call after A signer removal | Page confirmed completion and that signed bytes were discarded. |
| 5 | Removed A signer attempts A's configured call | Raw result `DENIED_UNCLASSIFIED`, HTTP 401, no code. The separate local control classifier records `CONTROLLED_PROVIDER_REFUSAL`. |
| 6 | B signer signs B's configured self-call after A removal | `SIGNED`; 228-byte result discarded |

The original raw denial records remain unchanged. The local classification is a separate evidence event. The vendor-specific reason for either HTTP 401 remains unknown because the response body was not retained.

After calls 1–3 and before calls 4–6, the owner removed A's signer once. One post-removal wallet check returned `MATCH/NO_ADDITIONAL_SIGNER`. The owner then completed call 4, the A self-sign control, once. Private counters record six sign attempts, one A removal, one owner-positive A attempt, five purpose wallet checks, and five owner verifications. The two failed A attachments and original analytics history remain preserved.

All configured transactions were type-2, chain `10143`, zero-value self-calls with empty data. The helper discarded signed bytes. No transaction was broadcast, no wallet was funded, and no chain write occurred. Additional spend was `$0`.

The local helper test suite passed `55/55`, including a synthetic regression that keeps A-on-B classification unclassified when A's saved wallet, signer, config binding, or transaction is missing or mismatched. Its production build and runner syntax checks passed. P16's offline qualification tests passed `12/12`; the P15, P02 and P04 regression checks also passed. These local checks do not replace independent review or the gate verdict.

## Scope and limits

This is direct provider evidence for the six one-owner sign-only controls and A signer removal. It does not prove cross-user application authorization, production authentication or storage, pending-record recovery, funded behavior, Kuru execution, Monad mainnet, swaps, transaction broadcast, or independent policy administration by an agent key.

The raw HTTP 401 denial does not name the provider's refusal reason. The separate classifier checks the expected negative-control stage and matching saved wallet, signer, transaction, and prior-control evidence. The report does not convert the raw denial into a provider error code.

The earlier analytics count of two requests against the one-request allowance remains in history. No counter was reset. Background request visibility remains limited to the retained observations and local ledgers.

P16 remains open pending two independent reviews of the exact candidate and the separate gate verdict. Do not use this result as a production-readiness claim.
