# Feature-map amendment proposal (waits for the shared lease)

The shared files `.agents/skills/verify-edge-os/feature-map.md` and `SKILL.md` are
reserved. This proposal is not applied. The controller applies it through the P05
shared-wiring lease.

## Proposed row

Add a row for the local durable scoped-stop domain. The row must state that the
mapped UI/browser path is not proof of the unwired stop feature.

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| P25 local durable scoped stops | not wired (local domain only) | none (local domain only); future owner-authenticated stop routes are `NOT_RUN` | owned `stops_local` schema: `scoped_stops` plus the reused `admission_local`, `execution_local` and `recovery_local` rows in the run-labelled test database | `apps/api/tests/stops/`; `docs/implementation/SCOPED_STOPS_PROFILE.md`; `docs/qualification/scoped-stops/` |

## Conditions

- The row states the local stage reuses the actual P22 admission, P23 execution
  and P24 recovery services, and is not provider enforcement, live admission, a
  real transport or an exactly-once network guarantee.
- The full mapped UI run in `verify-edge-os` does not prove this unwired feature
  and must not be recorded as its evidence.
- The SQL check must name the `stops_local` schema and the run-labelled test
  database, and must confirm the `public`, `admission_local`, `execution_local`
  and `recovery_local` schemas are separate.
- The row records that API/UI wiring and live transport evidence are `NOT_RUN`.
- A local stop is not signer removal, not liquidation and not evidence that all
  holdings are closed.
- Any production migration, route or UI is separate work under the lease.

Do not edit the shared map until the lease and a recorded integration step
authorize it.
