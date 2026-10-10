# Admission wiring checklist (deferred)

This is the future wiring work. None of it is done in the local stage. None of
these criteria may be marked PASS by the local stage.

## Not implemented here

- API routes that authenticate the owner and call `AdmissionService`.
- Persistence through a released production migration. The local stage uses the
  owned `admission_local` schema in the test database only.
- UI or browser surfaces.
- Live admission, execution, signing or provider calls.
- Provider enforcement or policy wrappers.

## Wiring prerequisites

1. **Owner authentication.** The route must derive `verified_owner_id` from the
   verified session and pass it to `AdmissionService`. It must reject any
   caller-supplied owner field.
2. **Approval source.** Replace authored approvals with the adopted, versioned
   mandate and approval snapshot. Keep the labeled-fixture path for tests only.
3. **Reconciled holdings.** Replace the authored holdings snapshot with
   reconciled account state. Unexplained external discrepancies must keep
   denying affected actions.
4. **Migration.** Move the owned tables into a reviewed shared migration under
   the P05 lease. Serialize with the other shared changes.
5. **Shared wiring lease.** P05 owns route, model registration, contracts and
   lockfiles. The controller serializes integration.
6. **Qualification.** Live admission stays closed until P21 (exit capacity and
   route restrictions) and the operational gates pass.

## Retained non-goals

- No duplicate execution attempt on replay or restart.
- Unknown outcomes keep reservations; no automatic replacement or fresh route.
- A local stop is not signer removal and not liquidation.
- Application checks are not provider enforcement of inventory.

## Evidence still required before live use

- P21 restriction, token mechanics, recipient and exit-capacity evidence.
- Operational gate evidence.
- Independent review of the wired API, migration and persistence path.
