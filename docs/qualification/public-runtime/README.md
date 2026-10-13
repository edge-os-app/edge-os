# Public runtime: local preparation (#58 Stage 2)

Milestone `RELEASE-E2E-L2-20261012-RUNTIME-LOCAL`. These documents describe what the application enforces locally and what a hosted deployment still needs. They are proposals and local evidence only. No host was selected or purchased, nothing was deployed, and no provider was called.

| Document | Purpose |
|---|---|
| [HOSTING_PROPOSAL.md](HOSTING_PROPOSAL.md) | Candidate topology, costs to confirm and residual unsupported controls |
| [RESTORE_ROLLBACK_RUNBOOK.md](RESTORE_ROLLBACK_RUNBOOK.md) | Migrate, restart order, restore, rollback; rehearsed locally |
| [RETENTION_DELETION_SUPPORT.md](RETENTION_DELETION_SUPPORT.md) | What the application keeps, what it cannot delete, and support facts |
| [RUNTIME_GUARDS.md](RUNTIME_GUARDS.md) | Quotas, rate and job limits, timeouts, startup and readiness checks |
| [ADVISORY_ASSESSMENT.md](ADVISORY_ASSESSMENT.md) | F6: npm advisories with reachability evidence |
| [KEYBOARD_QA.md](KEYBOARD_QA.md) | F5: keyboard check of the owned surfaces; screen-reader status |
