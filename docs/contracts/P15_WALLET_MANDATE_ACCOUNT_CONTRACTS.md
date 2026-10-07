# P15 wallet, mandate, and account contracts

Version 1.0.0 freezes the record meanings and offline examples for wallet ownership, trading permission, positions, actions, and monitoring. The machine-readable identity and state list is [contract.json](p15/contract.json). [Authored fixtures](p15/fixtures.json) and [the offline checker](p15/check_contract.py) show the contract with invented values.

Status: **decision contract frozen; runtime enforcement and provider mechanisms unqualified.** The checker proves only that these authored examples preserve the stated relationships. It does not prove app storage, Privy policy behavior, signing isolation, route support, transaction recovery, or financial safety.

## Identity and amounts

Every agent belongs to one verified owner and one user-owned wallet. Every intent, position, approval, and execution request binds to the owner, agent, wallet, network, exact strategy revision, and mandate. Name Monad 143 or testnet 10143 explicitly. Approval for one does not approve the other. A position also has a stable `position_id`. An action has a stable `action_id` and binds to one position or to an explicitly identified owner capital flow. The server derives `owner_id` from verified authentication. It does not trust a caller-supplied owner field.

An asset amount is `{ "asset_id", "raw", "decimals" }`. `raw` is a canonical non-negative base-10 integer string. It records the exact base-unit quantity. `asset_id` identifies the network and asset. `decimals` records the asset precision used to display the raw value. Records preserve all three fields. Code never adds amounts with different asset IDs. Native MON for gas stays separate from WMON and other trading assets.

P15 adds its own record content. It does not extend P02's closed record types. Persist each new record in the P02 envelope: `schema_version`, `record_type`, UUID `record_id`, UUID `owner_id`, `operation_id`, RFC 3339 UTC `created_at`, and `content`. The server derives the owner from verified identity and rejects a caller-supplied `owner_id`. P15 reuses P02 exact strings, units, revision/publication identities, lineage, and verified-owner boundary where those apply. The examples show domain state, not complete persisted envelopes.

## Wallets, ownership, and flows

An agent has one separately funded user-owned wallet. One wallet may hold several positions. A different agent's wallet supplies no funds, inventory, permission, or exit capacity. Account views may summarize multiple wallets, but they do not create pooled spendable balance or authority.

Wallet setup uses `REQUESTED`, `PENDING`, `UNKNOWN`, `CONFIRMED`, or `FAILED`. A timeout or lost response leaves setup `UNKNOWN`. Reconcile the original setup identity before retrying. A retry must not create a second wallet or overwrite the binding. Wallet creation grants no signer access and starts no trading.

Funding and owner transfers are capital flows. Each flow binds to the owner, agent, wallet, network, asset, raw amount, decimals, kind, state, and available transaction reference. A transfer is not a swap and does not consume a swap attempt. A pending or unknown flow does not count as complete and does not release a reservation. A confirmed deposit adds reconciled funds to that wallet. It does not activate the agent, raise allocation, replenish a consumed limit, remove a stop, or count as profit. A withdrawal does not sell an asset or stop the agent. Coordinate a reviewed withdrawal with that wallet's queue and reservations. Reconcile it before the affected agent acts again. An agent cannot transfer funds between agent wallets. An inter-wallet transfer requires explicit owner authorization and separate debit and credit flow records.

The initial accepted funding path supports a reviewed transfer from the owner's connected wallet or an agent deposit address. It covers the declared trading asset and native MON for gas. It does not select bridging, wrapping, card purchase, gas sponsorship, or automatic conversion. A wrong-network or unsupported asset stays visible and unavailable to the strategy.

Keep an immutable approval snapshot for each owner approval. Store its exact agent, wallet, network, strategy revision, mandate terms, adopted capital, limits, actions, expiry, stop effects, signer/policy binding, approval identity, and content hash. A later approval appends a snapshot and links it to its predecessor. It does not edit the prior snapshot. Current bindings identify which approved snapshot, signer, policy, and mandate govern new work.

## Mandates and admission

A mandate binds to one agent wallet, network, strategy revision, and immutable approval snapshot. The user reviews finite allocated capital, supported assets and routes, actions, expiry, risk limits, and stop effects together. The allocation does not equal the wallet's whole balance. Funding, login, research, and saved strategy drafts do not create trading permission. A broader mandate cannot enlarge the exact strategy rule. A strategy rule cannot exceed the mandate ceiling.

Keep these amounts separate for each wallet, asset, and applicable scope:

- allocated capital;
- cumulative buy input allowance in the declared quote asset;
- cumulative sell allowance in the declared base asset;
- consumed allowance;
- outstanding reservations;
- remaining allowance;
- action and swap-attempt budgets;
- native gas budget and actual gas;
- reconciled holdings and position-attributed inventory.

For each allowance, `remaining = approved - consumed - reserved`. Consumed plus reserved cannot exceed approved. Apply position and wallet checks atomically. The same funds or inventory cannot back two commitments. Each addition needs an adopted strategy and sizing rule, its own intent and receipt, updated cost basis, and full exit capacity. Admission requires both the strategy rule and mandate ceiling to allow the action. A broader mandate cannot enlarge a narrower strategy rule.

Before submission, recheck the exact preview, current strategy revision, mandate and policy binding, expiry, stop scope, current inputs, quote freshness, position, inventory, reservations, balances, and limits. A changed input or binding makes the preview stale. Deny it and require a newly reviewed preview. A quote is an estimate; it does not supply an acquisition upper bound where a separately adopted fixed token ceiling requires one.

An action keeps one identity through `PROPOSED`, `QUEUED`, `SUBMITTED`, `CONFIRMED`, `REVERTED`, `DENIED`, `CANCELLED`, or `SUBMISSION_UNKNOWN`. Cancel only before submission. Cancellation cannot undo a broadcast transaction. Count a broadcast-capable swap once as an attempt, including a revert. A confirmed success consumes reconciled input. A confirmed revert consumes actual gas. Release unused input only after reconciliation. A proved pre-broadcast denial consumes neither. Record denial reasons and update times. A confirmed receipt reconciles the action under the prior mandate. It creates no new permission. A timeout is not a failure verdict and never authorizes a duplicate.

## Queue, stops, and signer removal

Use one durable submission and reconciliation queue per agent wallet and network across all of its positions. The accepted initial implementation choice permits one unresolved economic transaction in that queue. Select eligible exits before unsubmitted entries or additions. Use a deterministic order within each priority class. Recheck eligibility at send time. A stale or expired queued intent must be denied and re-prepared through the approved review path. It must not be changed silently.

`SUBMISSION_UNKNOWN` retains the original signed transaction reference and hash, provider request references, and all reservations. Reconcile the original outcome before a second economic transaction. Record each transport request separately. A qualified resend reuses the same signed bytes and transaction hash and keeps the same economic action identity. A changed transaction is a new action and needs its own authority. If the transport cannot retrieve the original signed bytes and hash, resend remains unqualified. This behavior and delay suitability require runtime qualification. The queue for one agent does not block another agent's wallet.

A stop records its owner, scope (`POSITION`, `DEPLOYMENT`, or `AGENT_WALLET_NETWORK`), reason, creation time, denied actions, and any actions that remain eligible. `STOP_NEW_ENTRIES` denies entries and additions. Existing exits remain eligible only under explicit active authority. `HALT_ALL_SWAPS` denies new entries, additions, and exits. Monitoring and reconciliation continue for both modes. A stop can apply before the first position exists. A `Stop all agents` request creates one stop for each selected agent wallet. It does not create shared account authority.

Signer removal has its own `NOT_REQUESTED`, `REQUESTED`, `PENDING`, `UNKNOWN`, `CONFIRMED`, or `FAILED` state. A local stop does not prove provider removal. Pending or unknown removal blocks new agent submissions until the owner-authorized result and current wallet binding are reconciled. Confirmed removal blocks new agent submissions but preserves owner access, pending transactions, and residual holdings. The verified owner's recovery path remains available after signer removal. It has a separate authorization and audit record. Owner login or recovery does not restore agent permission. Neither renewal nor a new strategy revision restores removed authority. Restore operation only after separately approved owner rebinding and current signer/policy verification. Removal cannot undo a broadcast transaction.

Renewal appends terms and preserves the earlier mandate, consumed and reserved quantities, positions, pending actions, losses, and stops. An expiry extension changes time only. It does not replenish allowances. Additional authority needs explicit owner review and a verified updated policy binding. A reduction cannot erase an outstanding commitment. Restart, continuation after a trial, or receipt reconciliation cannot clear a stop or reset a limit.

## Position accounting and monitoring

Every acquisition, addition, partial exit, full exit, and owner capital flow remains a separate record. Each position has its own attributed inventory and cost basis. Use weighted average acquisition cost for that position. An addition updates units and basis. A partial exit removes the exited quantity multiplied by the average basis immediately before that exit. Realized result before fees equals reconciled exit proceeds minus the removed basis in the same quote asset. Record fees once under a qualified fee profile. The fixture gives an independent arithmetic example.

Keep reconciled realized result, estimated unrealized result, external capital flow, and actual native gas in separate fields. Use reconciled consideration and qualified trading fees for basis. Include gas in a common reporting unit only when a qualified conversion profile exists, and count it once. A deposit or withdrawal is not profit or loss. A mark is an estimate, not an achievable fill. Unknown required basis, cost, or mark stays `UNKNOWN`; it is never zero.

Return, account-value, and drawdown metrics remain unavailable until the builder adopts a versioned calculation and valuation profile with independent examples. Keep cumulative results, positions, and risk checks at their adopted wallet and position scopes. Do not add an unapproved threshold or valuation source.

Each monitoring record names the agent and wallet, operation state, last completed check time and result, next check time or blocking reason, pending actions, current permission summary, residual exposure, and evidence status. `RUNNING` says the worker runs. It does not say the strategy works. Monitoring shows recorded decisions and inputs. It does not expose private model reasoning or establish profitability.

## Enforcement and qualification boundary

| Layer | Contract obligation | Status and next qualification |
|---|---|---|
| Authenticated application | Derive owner from verified identity. Bind every action to its owner, agent, wallet, position, network, strategy revision, and mandate. | P03/P16 must test authenticated storage, cross-owner access, and per-agent isolation. |
| Application accounting | Enforce current approval, allocation, cumulative limits, reservations, attribution, queue, stops, freshness, and reconciliation. | Written behavior only. P16 and production-path P27 must test actual state, concurrency, restart, and denial. |
| Execution credential | Use only the approved current signer and policy binding. The executor cannot change policy. Keep policy administration credentials separate. | Credential separation, stale-binding denial, and owner recovery require focused implementation and security tests. |
| Privy policy | Independently limit the exact supported network, contract, methods, calls, and enforceable arguments. Deny arbitrary transfers, broad approvals, and unrelated calls. | Confirm each restriction against the chosen wallet type and deployed Flow ABI. Unknown restrictions block the affected capability. |
| Position inventory | Attribute confirmed approved acquisitions and additions. Exclude unrelated deposits and other positions. Avoid duplicate reservations or sales. | Privy identity or a broad token allowlist does not prove position accounting. P21 must qualify full intended exit capacity and the selected enforcement layers. |
| Removal and recovery | Preserve owner access and history. Block new work until removal or rebinding is verified. Reconcile pending transactions before recovery. | P16 and P20/Probe B must test actual signer removal, owner recovery, pending outcomes, and restart behavior. |

The application can check its ledger. Do not describe that check as independent wallet enforcement. Privy documentation describes wallet policies, signers, methods, networks, contracts, and transaction fields. The reviewed sources do not establish that a Privy policy reads Edge OS position inventory or reserves across positions. If a mandatory restriction needs a new approver or contract wrapper, return that architecture choice to the builder before implementation. P15 adds no approver or wrapper.

This ticket does not qualify a wallet provider, Monad deployment, Kuru route, asset mechanics, gas sufficiency, nonce handling, signer-removal timing, transfer race, or enforceable sell capacity. P16 qualifies wallet ownership and isolation. P20/Probe B qualifies the bounded Flow action. P21 qualifies exit capacity. Those tasks need actual mechanism evidence. Synthetic fixtures cannot pass them.

The remaining values and their consumers are explicit. Valuation unit, source, freshness, and loss thresholds feed P19, P24, P27, and P33. Flow route, token mechanics, fees, and full exit capacity feed P20 and P21. Signer and policy enforcement feed P16, P20, and P27. Owner transfer recovery feeds P16 and P27. Nonce, resend, unknown-outcome recovery, and queue-delay suitability feed P20 and P27. P15 selects no numeric production value for these inputs.

## Sources and provenance

Accepted behavior comes from the [Edge OS specification](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-activation-positions-and-shared-wallet-accounting), [build brief](../EDGE_OS_BUILD_BRIEF.md#wallet-accounting-and-enforcement), [ADR 0003](../adr/0003-durable-shared-wallet-accounting.md), [ADR 0005](../adr/0005-model-and-execution-authority-boundary.md), [ADR 0007](../adr/0007-separate-user-owned-agent-wallets.md), [ADR 0008](../adr/0008-python-api-postgresql-nextjs-privy-auth.md), the accepted [P01 identity profile](../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md), [P02 record contract](P02_FIRST_SLICE_RECORDS.md), [P02 compiler requirements](../research/P02_COMPILER_REQUIREMENTS.md), and the [wallet qualification checks](../EDGE_OS_RESEARCH_CONTRACTS.md#live-wallet-accounting-acceptance-checks).

Privy documentation was resolved through Context7 as `/llmstxt/privy_io_llms_txt` and checked with Exa against official pages on 2026-10-07. These pages are rolling documentation; they do not publish a version for this contract to pin:

- [HD wallets](https://docs.privy.io/recipes/hd-wallets) documents multiple embedded wallets for a user, including HD wallets from a shared seed. This is a possible route. It does not prove independent per-agent signing isolation.
- [Owners and signers](https://docs.privy.io/controls/authorization-keys/owners/overview) and [delegated permissions](https://docs.privy.io/controls/common-use-cases/delegation) describe owner control and policy-scoped signers. They do not prove the selected policy covers Edge OS accounting.
- [Policy overview](https://docs.privy.io/controls/policies/overview) describes wallet-request rules for supported methods, networks, contracts, and fields. It does not establish position-ledger access or cross-position reservations.
- [Remove signers](https://docs.privy.io/wallets/using-wallets/signers/remove-signers) documents owner removal of delegated signers. It does not cancel transactions already broadcast or qualify Edge OS's unknown-outcome recovery.

The pinned [Privy session-keys example](https://github.com/privy-io/examples/tree/7fcb04d54b528f4cf84bcc2064e7a698f9f3a7b5/examples/privy-next-session-keys) was inspected at commit `7fcb04d54b528f4cf84bcc2064e7a698f9f3a7b5`. Its example directory has an MIT license and declares `@privy-io/react-auth` `^3.12.0`. It also uses ZeroDev session keys. It was not installed or run, and no code was copied. Its provider, wallet, and policy behavior does not qualify this Monad path.

The pinned [Assensus source](https://github.com/degencodebeast/assensus/tree/02860cc5daf46d49f8b6a8ac8a524e0af7ac0b0a) was inspected at commit `02860cc5daf46d49f8b6a8ac8a524e0af7ac0b0a` from 2026-08-21. The tree did not expose a repository license. P15 uses only the task packet's portable lesson: explicit owner setup, restricted signer consent, saved submission references, and owner removal. No code or private archive is included.

## Run the offline example

From the repository root, run `python3 -B docs/contracts/p15/check_contract.py`. It uses only Python's standard library and the checked-in authored fixture. It does not load environment values, credentials, provider data, or a network connection. The checker proves example consistency and selected arithmetic. It does not exercise production enforcement or any runtime service.
