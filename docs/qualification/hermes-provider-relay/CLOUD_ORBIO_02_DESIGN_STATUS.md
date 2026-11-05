# CLOUD-ORBIO-02-DESIGN status

- Task: a design (not an implementation) for showing each study's model and tool budget in CREDIT, capping `max_tokens` on every call, and passing `max_cost` on future Orbio tool calls. Builder-approved normal cloud session, 2026-10-30.
- Branch: `cloud/orbio-02-credit-design`, from `origin/integration/edge-os-mvp` at `275b3992fdc620094586906ac1eada47e7d3b0ad`. Normal pushes only. No PR. Nothing was pushed to main or integration.
- Deliverable: `docs/qualification/hermes-provider-relay/ORBIO_CREDIT_DESIGN.md`.
- **Final design SHA: `c62cc3feb7e4bd5802f5b30529a345160a95d41f`** (the last commit that changes the design). The commit that adds this status file comes after it and changes only this file.
- No code changed. No provider call, no key, no spending.

## Independent review

One new, independent reviewer subagent checked the document against the code: every `file:line` claim, whether any cap was left out, the arithmetic, the 2b rule, and E1-COST1.

| Round | Candidate | Verdict | Findings | Disposition |
|---|---|---|---|---|
| 1 | `72efa90` | REVISE | F1 BLOCKING: the cap of one provider request per turn was left out of section 1.1. F2-F7 NON-BLOCKING: external provider cap h8; two missing equality checks in C2; no ledger reader for `max_output_tokens`; `min_output_tokens >= 1`; `held_credit` is only a lower bound and `usd()` returns a `$` prefix; under option A a mismatched call blocks its study's scope. All other `file:line` claims TRUE; arithmetic correct. | All repaired in `a036012` and `e24fc72`: rows C9 and C10 added, plus the notes. |
| 2 | `e24fc72` | **PASS** | F1-F7 resolved. One new NON-BLOCKING note: C9 also cited `relay_service.py:384-387`, but that guard is built fresh for each request and does not count requests. | Fixed exactly as the reviewer suggested in `c62cc3f`. That one-line citation change was not re-reviewed. |

## Not done, and why

- Orbio's public pages (`www.orbio.so`, `/developers`, `/llms.txt`, `/protocol/agents.md`, `/api/v1/tools`) could not be read: the host does not resolve under this session's network policy. The design uses only the brief's two facts: 1 CREDIT = USD 1, and tool calls take `max_cost`. To read the pages, allow `www.orbio.so` in the cloud environment's network settings.
- `cloud/orbio-01-route` was not on the remote, so its file list was not checked. The overlap in section 4 of the design is inferred and must be compared with its real diff after it merges.

## Open questions for the builder

1. **Settlement decision (design section 3).** Keep E1-COST1, or extend it? Recommendation: keep E1-COST1 now (option A). After one approved paid call shows that Orbio's balance change equals `usage.cost`, adopt option C: settle at the higher of the reported cost and the token-priced charge. Not option B, whose failure mode is silent overspend past the shared USD 2.00.
2. Is a study's budget the owner's shared USD 2.00 (as designed), or should there be a new per-study cap?
3. `min_output_tokens` for the release: the smallest useful output limit (at least 1).
4. Orbio `max_cost`: its unit and precision, what it covers, what happens when it would be exceeded, and what cost a tool reply reports and how it is reconciled.
5. Should `CONTEXT.md` gain a glossary entry for **CREDIT** (Orbio's unit, distinct from Nansen credits and from the avoided term "AI credits")?
6. Order: parts 2a and the ledger half of 2b can start now. The relay half of 2b waits for CLOUD-ORBIO-01 to merge. Part 2c waits for decision 1 and question 4.
