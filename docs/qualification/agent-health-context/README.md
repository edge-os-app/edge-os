# Agent health and context agreement preparation (P31)

Milestone `P31-HEALTH-CONTRACT-L3-20261012-01v1`. Base `f84ef415278196db2c8bba73eaa154a1ef00748b`,
tree `91cc55446a6d2dc3672cd153a0bec225a3fed009`, branch `ticket/p31-health-contract`.

These documents agree one read-only contract for agent health and for the exact context a P31
conversation attaches to a saved record. They are a preparation milestone only. They enable no
application, chat, scheduler or live action. No producer is implemented here and no runtime
capability is proved.

## Status of each claim

| Status | Meaning in these documents |
|---|---|
| `PRESENT (f84)` | The field and its caller exist in the accepted base and the saved record holds it |
| `MISSING` | The accepted requirement needs the field, but no accepted producer saves it today |
| `PROPOSED` | This agreement requests the field; the owning lane must implement and prove it |
| `NOT_RUN` | No runtime, provider, model, host or browser check was performed for this milestone |

## Documents

| Document | Responsibility |
|---|---|
| [HEALTH_PROJECTION_CONTRACT.md](HEALTH_PROJECTION_CONTRACT.md) | One versioned read-only projection for direct views and P31 conversation; worker health, trading results and edge evidence stay distinct |
| [CONTEXT_AND_PREVIEW_AGREEMENT.md](CONTEXT_AND_PREVIEW_AGREEMENT.md) | Exact read-only context and preview agreement for the supported accepted controls only |
| [SOURCE_RECORD_MAP.md](SOURCE_RECORD_MAP.md) | Traces every projected field to an accepted caller, table, record or current test, or marks it `MISSING`/`PROPOSED` |
| [WORKED_CASES.md](WORKED_CASES.md) | Independently worked unsigned cases and their expected direct/conversation agreement |
| [worked_health_cases.json](worked_health_cases.json) | Machine-readable unsigned fixtures for those cases |
| [LANE2_INTEGRATION.md](LANE2_INTEGRATION.md) | Producer/consumer handshake, the next separately owned P31 surfaces and the mounted checks still required |

## Boundaries

- P31 stays blocked by P27. This documentation does not complete P31, P27 or issue #58.
- The canonical P27 producer is not implemented. Every scheduler, standing-permission and
  forward-feed field below is `MISSING` and carries a producer obligation.
- Current financial records override stale context. Clearing or disabling context omits memory
  but keeps the required owner, safety and permission state.
- Manual sale (P32) and every unqualified operation stay unavailable. A preview is not
  execution permission.
- The evidence for this milestone lives outside the repository at
  `.scratch/p31-health-contract/evidence/`. It records the exact activation, checks and both
  original internal assessments.

## Source authorities

- Spec: `docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md`, "Accepted research
  declaration and agent monitoring handoff" and "Accepted account views and contextual
  conversation"; stories 65-70 and 79-80.
- Release ticket: `docs/planning/EDGE_OS_USER_RELEASE_TICKET_2026-10-12.md` (controller workspace;
  portable body on GitHub issue #58), AUT06, IC01-IC08.
- Accepted implementation: `docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md`.
- Accepted contracts: `docs/EDGE_OS_RESEARCH_CONTRACTS.md` (WAL-Q26), the thin per-agent memory
  contract (MEM-Q02-MEM-Q05) and issue #39 (`P31`).
