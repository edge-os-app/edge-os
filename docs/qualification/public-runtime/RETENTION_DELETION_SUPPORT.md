# Retention, deletion and support: proposal from implemented facts

Status: proposal. The facts below describe the current code. The policy choices are open for the builder.

## What the application keeps today

- **Kept indefinitely:** every owner-scoped record stays in PostgreSQL. No job removes old rows.
- **Append-only history:** a database trigger (`edge_os_reject_change`) refuses updates and deletes on many history tables. Examples:
  - investigation declarations and access history;
  - effect comparisons and reports;
  - replay runs and configurations;
  - interpretation attempts and settlements;
  - wallet-setup events;
  - research events and reports;
  - `usage_local.usage_events`.
- **Original actions:** financial actions, receipts, reservations and recovery cases keep their original lineage, so later reconciliation reads the original action.
- **Usage:** quota allocations and reservations are never reset. A settled reservation keeps what it booked.
- **Request windows:** `usage_local.request_windows` keeps one row per owner per minute with writes. These rows are not used after their minute. A cleanup job is a proposal below.
- **Logs:** the API logs error class names, not request bodies, tokens or key values. The hosting platform keeps its own logs under its own terms.

## Deletion

- No API route deletes owner data. No owner can ask the application to erase a record.
- An operator cannot delete append-only rows without dropping the trigger, which is a schema change.
- Removing an agent (`Request removal`) withdraws its signer and stops new work. It keeps the agent's history and does not touch the wallet or its holdings.
- Data at a provider (wallet provider, market data, model provider) follows the provider's terms. The application makes no deletion promise for it.

## Proposals (not implemented, for decision)

1. State in the public terms that records are kept for the life of the deployment, because the financial and research history must remain checkable.
2. Add a request-window cleanup that removes windows older than one day. They hold no history.
3. If account erasure becomes a requirement, design it as a separate reviewed change. It must keep the financial lineage needed for reconciliation, or record why it may go. It must name the provider data it cannot reach.
4. Keep backups under the same retention period as the database. Restores bring back everything in the backup.

## Support facts for a support page

- A lost reply or a failed read after a saved change leaves the screen paused with "Check saved …". The owner repeats the read, not the change.
- 429 `rate_limited` means too many changes in one minute; the reply says how long to wait.
- 409 `too_many_active_jobs` means the owner has the maximum number of waiting or running research jobs.
- `BUDGET_EXHAUSTED` means the owner or the shared total allowance is used. Unknown usage stays counted until it is settled, and nothing resets automatically.
- 503 with `quota_cap_mismatch` is an operator problem: a configured cap differs from the frozen cap.
- No support channel, contact address or response time exists yet. That is a builder decision.
