# Feature-map amendment proposal (waits for the shared lease)

The shared files `.agents/skills/verify-edge-os/feature-map.md` and
`SKILL.md` are reserved. This proposal is not applied. The controller applies
it through the P05 shared-wiring lease.

## Proposed row

Add a row for the local admission domain. The row must state that the mapped
UI/browser path is not proof of the unwired admission feature.

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| P22 local admission and reservations | not wired (local domain only) | none (local domain only); future owner-authenticated routes | owned `admission_local` schema: `admission_decisions`, `admission_allowances`, `admission_reservations`, `admission_positions` in the run-labelled test database | `apps/api/tests/admission/`; `docs/implementation/ADMISSION_RESERVATIONS_PROFILE.md`; `docs/qualification/admission/` |

## Conditions

- The row states the local stage is application accounting, not provider
  enforcement or live admission.
- The full mapped UI run in `verify-edge-os` does not prove this unwired
  feature and must not be recorded as its evidence.
- The SQL check must name the `admission_local` schema and the run-labelled
  test database.
- Any production migration, route or UI is separate work under the lease.

Do not edit the shared map until the lease and a recorded integration step
authorize it.
