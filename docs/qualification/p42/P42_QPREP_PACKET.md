# P42 numerical-preparation packet

Task: `P42-QPREP-20261013-01` (issue #28)
Authority: issue #28's 2026-10-13 bounded local-preparation assignment
Assignment starting base: `02827e464e6f9a251bd69d607c1c53c1d028cfa2`
Assignment base tree: `2ba5bf79c07111679015766cd0d5720781c844d4`
Rebased integration parent before calibration: `c4bc2a405f872ad284639a8de84712f7bc569b0f`
Branch: `quant/p42-statistical-preparation`
Checkout: `/Users/kaluarunsi_1_2/.codex/worktrees/p42-statistical-preparation/edge-os`

Pre-experiment profile revision: `edge-os.stat-q01-qprep/2026-10-16.1`.
Prior `2026-10-13.1` and `2026-10-14.1` proposals were not evaluated. This
revision freezes the complete-family schedule guard, append-only pre-label
holdout event, SHA-256 lineage checks, total work cap, ambient-Decimal-safe
generator, exact-family finalist binding, and per-series/per-history coverage
assessment before calibration begins.

The first bounded run on source `7e99be8912a03e3224f298532d1b5f8676d8f3f8`
remained `UNRESOLVED`. A later repeat found that raw artifact SHA-256 included
volatile elapsed-time and allocation telemetry. Source
`530c09a3811db8b12124c1d45b3f899a16e15526` added a schema-v2 deterministic
calculation fingerprint without changing the frozen numerical profile, plan,
seeds, criteria, or limits; that rerun remains `UNRESOLVED`. Its raw result and
report are retained unchanged as
[`CALIBRATION_RESULT_2026-10-14.2.json`](CALIBRATION_RESULT_2026-10-14.2.json)
and
[`CALIBRATION_REPORT_2026-10-14.2.md`](CALIBRATION_REPORT_2026-10-14.2.md).
The `/2` coverage Wilson interval incorrectly pooled dependent within-history
outcomes. This new candidate uses a new profile, frozen plan, result schema `/3`,
and bounded run; it must not retroactively reinterpret the historical run.
It preserves the outer seed lists, but its new profile identity intentionally
changes the derived bootstrap/IID seed namespace; the `/3` run is a separately
identified experiment.

## Transport and boundaries

This uses the portable contributor route: the draft PR is the return transport;
pane/Goal/Smux activation is inapplicable. The controller will arrange two
independent exact-candidate reviews and the separate gate. Main merge,
integration, shared runtime adoption, market/provider/model calls, protected
holdout access, wallets, and paid compute are outside this packet.

Owned new paths before editing:

- `apps/api/src/edge_os_api/research/statistical_preparation.py`
- `apps/api/src/edge_os_api/research/statistical_partition.py`
- `apps/api/src/edge_os_api/research/statistical_calibration.py`
- `apps/api/tests/test_statistical_preparation.py`
- `apps/api/tests/test_statistical_calibration.py`
- `apps/api/tests/test_statistical_partition.py`
- `docs/implementation/STAT_Q01_CANDIDATE_PREPARATION_PROFILE.md`
- `docs/qualification/p42/`

Accepted P09 modules, API/database/UI/jobs wiring, contracts, replay/P14, and
market data are preserved. Historical helper commit
`9134efb37a45e6c0eaaa380a4527ccea0787ff8e` is disclosed proposal input only;
its review does not approve this replacement.

## Skills and adaptations

Host catalog inspected 2026-10-13. Applied:

- `tdd`, `/Users/kaluarunsi_1_2/.codex/skills/tdd/SKILL.md`: public-interface,
  vertical-slice tests for the isolated numerical module.

Required-by-issue instructions unavailable in this host catalog:
`quantitative-research`, `python-pro`, `python-code-style`,
`python-anti-patterns`, `karpathy-guidelines`, `ponytail`,
`general-review-protocol`, `review-verification-protocol`, `code-reviewer`,
and `code-review-excellence`. The adaptation is to follow the accepted Decimal
and P09 conventions, use standard-library-only code, preserve explicit failure
states, and record those unavailable instructions for the controller/reviewers;
it does not waive their required independent review route.

## Required evidence

Focused module/generator tests run during changes; final candidate runs all
three new suites, the affected P09 suite, independent-reference and ambient-Decimal
checks, `git diff --check`, scope/ancestry checks, and the bounded calibration
from the frozen plan. The final PR records exact commands, runtime, resource
outcome, source hashes, candidate commit, original reviewer reports, and
limitations. Any insufficient or failed calibration remains `UNRESOLVED`.
