# Feature-map amendment proposal (waits for the shared lease)

The shared files `.agents/skills/verify-edge-os/feature-map.md` and
`SKILL.md` are reserved. This proposal is not applied. The controller applies it
through the P05 shared-wiring lease.

## Proposed row

Add a row for the local evaluation/queue domain. The row must state that the
mapped UI/browser path is not proof of the unwired execution feature.

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| P23 local evaluation and exclusive queue | not wired (local domain only) | none (local domain only); future owner-authenticated routes | owned `execution_local` schema: `execution_decisions`, `execution_intents`, `execution_queue`, `execution_claims`, `execution_submission_attempts` in the run-labelled test database | `apps/api/tests/execution/`; `docs/implementation/EXECUTION_QUEUE_PROFILE.md`; `docs/qualification/execution/` |

## Conditions

- The row states the local stage reuses the actual P06 compiler and P22
  admission service and is not provider enforcement, live admission or a real
  transport.
- The full mapped UI run in `verify-edge-os` does not prove this unwired feature
  and must not be recorded as its evidence.
- The SQL check must name the `execution_local` schema and the run-labelled test
  database, and must confirm the `public` and `admission_local` schemas are
  separate.
- Any production migration, route or UI is separate work under the lease.

Do not edit the shared map until the lease and a recorded integration step
authorize it.
