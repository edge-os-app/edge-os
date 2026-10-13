# Feature map proposal: LOCAL Docker rehearsal

Proposal only. Lane 2 owns `.agents/skills/verify-edge-os/feature-map.md` in this wave; this file does not edit it. The row below names the separate rehearsal driver; it does not join `scripts/p03/verify_run.py`.

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| LOCAL Docker packaging, restore and restart (#58 DOCKER-REHEARSAL-L4) | Accepted `research-history-journey`, `research-history-report` and `recurring-journey` specs seed through the packaged web; `tests/deployment_rehearsal/browser/saved-identity-reopen.spec.mjs` reopens the saved report, jobs, held unknown liability, revision, labelled replay and recurring deployment with GET requests only, at 1280px and 390px, with keyboard, labels, overflow and an other-owner refusal, after process replacement and again on the restored stack | Same routes through the loopback entry (`deploy/local/public_entry.py`); `/healthz`, `/readyz` | Every table in `public` and each `*_local` schema (row count and content hash) plus named owners, requests, revisions, reports, replays, deployments, jobs, caps, reservations and held unknown, compared seeded → after replacement → after reopen → restored → after restored reopen | `<evidence>/<run_id>/steps.json`, `identities/*.json`, `image-identities.json`, `image-secret-scan.json`, `topology-*.json`, `browser-*/evidence/`, `resources-before.json`, `resources-after.json`, `summary.json` |

Command: `apps/api/.venv/bin/python scripts/deployment_rehearsal/rehearsal_run.py --evidence-root <private folder>` (see `deploy/local/RUNBOOK.md`). Guards: `cd apps/api && .venv/bin/python -m pytest ../../tests/deployment_rehearsal`.
