# Feature-map amendment proposal (waits for the shared lease)

The shared files `.agents/skills/verify-edge-os/feature-map.md` and
`SKILL.md` are reserved. This proposal is not applied. The controller applies it
through the P05 shared-wiring lease.

## Proposed row

Add a row for the local original-action recovery domain. The row must state that
the mapped UI/browser path is not proof of the unwired recovery feature.

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| P24 local original-action recovery | not wired (local domain only) | none (local domain only); future owner-authenticated routes | owned `recovery_local` schema: `recovery_cases`, `recovery_evidence` plus the reused `execution_local` and `admission_local` rows in the run-labelled test database | `apps/api/tests/recovery/`; `docs/implementation/ACTION_RECOVERY_PROFILE.md`; `docs/qualification/action-recovery/` |

## Conditions

- The row states the local stage reuses the actual P06 compiler lineage saved by
  P23 and the P22 admission service, and is not provider enforcement, live
  admission, a real transport or an exactly-once network guarantee.
- The full mapped UI run in `verify-edge-os` does not prove this unwired feature
  and must not be recorded as its evidence.
- The SQL check must name the `recovery_local` schema and the run-labelled test
  database, and must confirm the `public`, `admission_local` and `execution_local`
  schemas are separate.
- The row records that live transport evidence is `NOT_RUN`.
- Any production migration, route or UI is separate work under the lease.

Do not edit the shared map until the lease and a recorded integration step
authorize it.
