# Recurring operation (P27 LOCAL)

Status: **LOCAL composition only.** #58 milestone `RELEASE-E2E-L2-20261013-P27-LOCAL-v1`. The application creates and processes repeated durable evaluations while the user's browser is closed, through the existing job engine, admission, wallet claims, stops, removal and original-action recovery. Every observation, quote, holding, transport and receipt is an authored fixture (`SYNTHETIC_FIXTURE`). Production keeps the unavailable ports, so it cannot activate a deployment. This is not an operating profile, a forward feed, financial permission or evidence of an edge.

- Frozen contract: [CONTRACT.md](CONTRACT.md). Profile section: `docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md`, "P27 LOCAL".
- Proposed hosted/live packet (nothing run): [HOSTED_RECURRING_PACKET.md](HOSTED_RECURRING_PACKET.md).

## What a user can do locally

1. Adopt exact bounded terms for a funded agent (unchanged flow).
2. Open the agent's Positions view and start recurring operation with an explicit authorization bound to the adopted terms hash.
3. Close the browser. The producer process saves one evaluation per due five-minute slot, reconciles unknown originals from receipts, and advances its occurrences through the existing worker stages.
4. Reopen and read the durable record: the last scheduler pass, the saved and next due slot, missed slots (never replayed), each slot's saved outcome with input and evaluation times, submissions, pending reconciliation and one wait reason.
5. Stop new entries, halt all swaps, request removal or end recurring operation. These controls persist across restarts. Ending also releases admitted, unsent work; none of them sells, cancels a sent action or releases unknown liability, and an unknown action is still reconciled from its receipt after an end.

## Processes

- `python -m edge_os_api.execution.recurring_producer --once` (one pass) or `--interval S [--max-passes N]` (persistent, ends on SIGTERM after the current pass). Schema drift exits 3 before any effect.
- The existing bounded worker (`python -m edge_os_api.execution.worker`) still advances manual evaluations. Either process may advance an occurrence; the per-job lock lets only one hold it.
- `--clock-offset-minutes` exists only for LOCAL fixture verification and is refused in any other mode.

## Proof in this candidate

- API: `apps/api/tests/test_recurring_operation.py` (own database; separate-process producers; fault matrix in the profile).
- Web: `apps/web/tests/agent-recurring.test.tsx`.
- Mapped verifier: `scripts/p03/recurring_phase.py`, `tests/p03/recurring-journey.spec.mjs`, `tests/p03/recurring-report.spec.mjs` (two owners; browser closed during producer passes; contention; missed slots; stop; removal; end; restart).

## Retained limits

- No actual forward observation source exists. `forward_observation_from` still returns UNAVAILABLE for every historical, recorded and Nansen source, and the fixture market is the only forward class the fixture mode accepts.
- Missed-slot policy, freshness bound and five-minute grid are LOCAL choices, not a qualified production operating profile.
- New terms for an agent need a new agent setup (one consent review per agent and revision), so an ended deployment does not restart on the same agent.
- P31 conversation health is not consumed; it may read the same projection only after its own accepted assignment. AUT08 hosted/live proof is NOT_RUN.
