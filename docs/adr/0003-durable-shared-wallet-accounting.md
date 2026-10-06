---
status: accepted
---

# Preserve accounting across deployments and permission changes

**Partially superseded, 2026-10-05:** [ADR 0007](0007-separate-user-owned-agent-wallets.md) replaces the shared-wallet architecture with one separately funded wallet per trading agent. This record preserves the earlier decision and rationale. Durable cumulative accounting, reservations, position attribution and renewal rules remain accepted within each agent wallet; they do not authorize sharing funds between agents.

The builder accepted multiple positions, coordinated shared-wallet reservations and durable cumulative accounting on 2026-10-03, amended Q22 and Q25–Q30. The wallet's funds cannot back competing commitments. Continuation, recovery and renewal preserve consumption, reservations, positions and losses; additional authority is explicit. A separate ledger per deployment or reset on renewal would be simpler but could double-allocate funds or erase used permission.

The [specification](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-activation-positions-and-shared-wallet-accounting) owns the accounting rules; [WAL-Q01–18](../EDGE_OS_RESEARCH_CONTRACTS.md#live-wallet-accounting-acceptance-checks) remain unrun. The initial submission queue is a temporary implementation choice, not a permanent one-position/concurrency restriction. Q31 selects inventory-based exit permission as intended behavior, subject to enforcement/capacity qualification; an additional fixed quantity ceiling requires its applicable acquisition bound. This ADR selects no new approver, contract wrapper or qualified execution mechanism and grants no implementation or financial approval.
