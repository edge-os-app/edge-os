# P42 numerical-preparation packet

Task: `P42-QPREP-20261013-01` (issue #28)
Authority: issue #28's 2026-10-13 bounded local-preparation assignment
Base: `02827e464e6f9a251bd69d607c1c53c1d028cfa2`
Base tree: `2ba5bf79c07111679015766cd0d5720781c844d4`
Branch: `quant/p42-statistical-preparation`
Checkout: `/Users/kaluarunsi_1_2/.codex/worktrees/p42-statistical-preparation/edge-os`

Pre-experiment profile revision: `edge-os.stat-q01-qprep/2026-10-14.1`.
The prior `2026-10-13.1` proposal was not evaluated. This revision freezes the
explicit comparison cap, dependent-null IID diagnostic, timestamp-boundary
fixture, and pre-label holdout access state before calibration begins.

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

Focused module/generator tests run during changes; final candidate runs both
new suites, the affected P09 suite, independent-reference and ambient-Decimal
checks, `git diff --check`, scope/ancestry checks, and the bounded calibration
from the frozen plan. The final PR records exact commands, runtime, resource
outcome, source hashes, candidate commit, original reviewer reports, and
limitations. Any insufficient or failed calibration remains `UNRESOLVED`.
