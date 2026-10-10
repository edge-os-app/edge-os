# Local verification and feature-map proposal

Deliverable under Ownership and outputs. Prepared 2026-10-10. This is a proposal only. It changes no shared verifier or feature-map file.

## Public command and interface

- Default command: `python3 -B docs/qualification/route-restrictions/restriction_checker.py`.
- Test suite: `python3 -B -m unittest discover -s docs/qualification/route-restrictions -p 'test_*.py' -v`.
- Capacity check: `python3 -B -m unittest docs/qualification/route-restrictions/test_capacity_examples.py -v`.
- Public interface: `evaluate_declared_case(profile, action)`, `profile_readiness_reasons(profile)`, `load_profile(mapping)`, `load_action(mapping)`.

## Local fixture and evidence identities

| Item | Identity |
|---|---|
| Fixtures schema | `p21-route-restrictions/1` |
| Fixture file | `docs/qualification/route-restrictions/fixtures.json` |
| Candidate | committed on `ticket/p21-route-restrictions` |
| Result classes | `AUTHORED_FAKE_ONLY` or `BLOCKED` only |
| Provider flag | `provider_executed: NOT_RUN` |

## Absent changes

- No UI, API route, SQL migration, lockfile or shared configuration change.
- No application, verifier, script or feature-map file change. The shared verifier and map stay read-only under the P05 lease.
- No wallet, provider, signing, network or financial path.

## Future live verification (separately enabled)

A live verification step is a **separate, explicitly enabled** proposal. It is not implemented here. It would run only under a released bounded packet (`LIVE_TEST_PACKET.md`) and would add, at that time:

1. a read-only deployed-bytecode identity check for the entrypoint and router;
2. a frozen quote/build response capture;
3. a receipt and asset-delta capture for one controlled swap;
4. a denial, recovery and removal observation set.

Each step keeps its own ceilings, stop conditions and cleanup. This proposal grants no live authority.
