# UI copy rules

Status: draft for PLAIN-COPY-L1-20261030. Accepted wording changes only after controller ANSWER1.

This file governs every user-visible string in `apps/web`. It keeps the product honest: plain words in the main text, proof data in a collapsed Details control, and no safety fact weakened.

## 1. Plain English rules

- Write short sentences. One idea per sentence.
- Use the active voice: "The server saves the plan", not "The plan is saved by the server".
- Use common words. Give each word one meaning (see the fixed terms below).
- Write to the person as "you". Write about the product as "we" or "the server".
- Use a verb for an action. Do not turn verbs into long nouns.
- Put the point first. Put the condition or reason after it.
- Use "must" for a rule, "can" for a possibility, "cannot" for a refusal.
- Do not use jargon, slang or metaphors.
- Do not use more than three nouns together. Split the phrase.
- Do not use a contraction when the sentence is a refusal or a limit. Write "cannot", "does not", "is not".
- Keep a safety statement in the main text. A safety statement is a limit, a refusal, an unknown value, "not claimed", "no trading permission", or "no study ran".
- Keep "Unknown" as "Unknown". Never show "0" for an unknown value.

## 2. Fixed terms (one word per meaning)

| Concept | Use | Do not use |
|---------|-----|------------|
| The model that reads words | research agent | interpreter, interpretation, inference, reading |
| A saved request reply | answer | response payload |
| A saved strategy snapshot | saved version | revision, immutable revision |
| A saved investigation plan | plan | declaration, pre-outcome declaration |
| A saved rule and its limits | rule | declaration |
| A replay of saved price data | replay | run, comparison (except the effect comparison screen) |
| The effect comparison screen | comparison | run, replay |
| One check of a rule | check | evaluation, bounded evaluation |
| Recorded or authored input data | saved data or example data | dataset, fixture, synthetic recording |
| The group of provider responses | saved responses | recorded responses, payload |
| A chain of saved steps | steps | events, event codes |
| A five-minute market period | five-minute period | bucket, source bucket |
| A locked internal setup | locked research setup | operating release, data setup, release id, profile |
| A group of time | time period | partition, temporal partition |
| The person's saved permission | permission | consent, mandate |
| The right to trade | trading permission | execution authority, capital authority |
| Money held for a later action | reserved amount | reservation, hold |

Vendor names stay as they are: Monad, Kuru, Envio, Nansen, Privy, QuickNode, WMON, MOE.

## 3. Banned from the main text

Move each of these into the panel's Details control. Do not delete it.

- Release ids and release names (the main text says "locked research setup"), for example `actual-moe-history2h-nansen-20261022/1`.
- Hashes and hash prefixes: SHA-256, content hash, manifest hash, request hash, delivery hash, report hash, handoff hash, rule-map hash.
- Enum states and event codes: `JOB_QUEUED`, `BUDGET_RESERVED`, `PROVIDER_ACTUAL`, `VERDICT_LIMITED`, `PASS`, `MISMATCH`, `FIXTURE_QUALIFIED`, `NEVER_ACTIVE`, `CHANGE_APPLIED`, and similar.
- Raw API field names: `all_holders`, `token_amount`, `top_100_holders`, `provider_requests`, `compute_seconds`, `deadline_seconds`, `creator_history`, `wallet_pnl`, `social_signals`.
- Package, profile and fixture ids: `p12.spot-replay/1`, `p13.wc01/1`, `edge-os.delayed-history-replay/1`, `synthetic-effect-comparison/1`.
- Table names, column names and internal source labels.
- Internal codes for clients, transports and routes: `P07_HTTP_CLIENTS_*`, `KURU_FLOW_FIXED_INPUT`, `PROVIDER_ACTUAL`, `SYNTHETIC_FIXTURE`, `AUTHORED_RECORDING`.
- Error and reason codes: `parent_revision_conflict`, `interpretation_revision_conflict`, `wallet_policy_refused`, `FILL_UNAVAILABLE`, `NO_NEXT_BUCKET`.
- Raw ids in a label position: declaration id, revision id, job id, evaluation id, trial id, dataset id, run id. A short id inside a Details table is allowed.

Addresses, transaction hashes and amounts are data, not jargon. They may stay in the main text when the person needs them to act. If the style guide and a safety need conflict, the safety need wins and the value stays visible.

## 4. Numbers and plurals

- Write numbers as digits for counts and quantities: "3 checks", not "three checks".
- Use the plural helper for every count word. One shared helper lives in `apps/web/lib`. It returns the count, the singular for 1 and the plural for every other number, including 0.
- Do not write "(s)", "page(s)", "bucket(s)" or "N record(s)".
- Write a range with "to": "12:05 to 12:35 UTC".
- Keep exact decimals as stored. Do not round money, amounts or thresholds.
- Use "at most" and "up to" for a maximum. Use "at least" for a minimum.
- Use "N of M" for a part of a whole. Do not write "N / M".

## 5. The Details rule

- Each panel that loses proof data gets one collapsed Details control.
- Use the shared control. It wraps native `<details>` and `<summary>`. Do not add a dependency.
- The summary label is plain: "Details", "Proof data" or "Saved proof". Choose one label per panel and keep it stable.
- Details is collapsed by default. A proof value is findable, not hidden.
- Nothing is deleted. Every value that the old text showed must be in the panel's main text or in its Details.
- A safety statement stays in the main text. Limits, refusals, unknown costs, "not claimed", "no trading permission", "no study started", and the research-agent-unavailable state never move into Details only.
- If a panel had no Details control before and loses proof data, add one. If a panel already has a matching Details control, reuse it.

## 6. Required safety statements

Keep these in the main text of the named screen. The words may change; the meaning must not.

- Research home: preparing words may cost model money; it does not start a study or authorize a trade.
- Investigation plan: saving records a plan before any result is read; it does not read data, run a study or start a trade; $0 paid access.
- History investigation: the chosen source is example data unless the server says it uses the real setup; results are descriptive and grant no trading permission.
- Nansen report: stand-in or example responses are not provider data, market evidence or a trading signal; holder records are a partial list; flow records do not show buying or profit.
- Market adoption: trading stays unapproved; no trading permission is granted.
- Spot replay: fills are assumptions; gas, spread, extra impact and capacity are not modelled.
- Wallet setup: saving the setup creates no wallet; one creation attempt; a repeat never creates a second wallet.
- Agent authority: adopting terms saves an inactive permission; it never signs, moves funds or grants wallet permission by itself; the USD ceiling is not available.
- Agent funding: a saved deposit plan is not a sent or credited transfer; current holdings may be unavailable; no balance is assumed.
- Agent actions: a stop does not sell, withdraw or cancel a sent action; removal keeps the person's access to the wallet and holdings; reconciliation never sends a replacement.
- Recurring operation: ending stops new slots and releases unsent work; it does not sell, cancel a sent action or release unknown liability; example data only.
- Account views: example records, not live wallet data; the build does not connect a wallet or move funds; account value, percent return and drawdown are unavailable.
- Agent health: answers come only from saved records; asking changes nothing, calls no provider and grants no permission.

## 7. Review checklist

Before a copy change is ready for review:

1. Does the main text state the same fact as the old text?
2. Is every removed value in the panel's Details control?
3. Is every limit, refusal, unknown value and "not claimed" still in the main text?
4. Does each count use the plural helper?
5. Is each fixed term used with one meaning?
6. Is every banned term out of the main text?
7. Did the change avoid the API text, saved values, hashed values and behaviour?
8. Does the test check the fact, the Details value or the refusal, not the exact old wording?
