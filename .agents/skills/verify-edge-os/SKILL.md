---
name: verify-edge-os
description: Verify Edge OS end to end on a fresh isolated instance. Use after a feature change, before claiming a runtime slice done, when repeating another agent's verification, or when inspecting saved records, evidence and cleanup.
---

# Verify Edge OS

Run the mapped path on a fresh instance, read the saved records yourself, keep the evidence, clean up only what the run created. [feature-map.md](feature-map.md) lists each feature, its UI route, API route, SQL check and evidence file. Fixtures stay fixtures: a pass here proves no real model, no real Privy login, no research run and no wallet behavior.

## Run

Work from the repository root. Each step names its own done condition. The whole run is done when step 3's final JSON line says `"ok": true` and steps 4 to 6 meet their conditions.

1. **Preflight.** Done when `docker info` answers, `uv`, `node` 24 and `npm` exist, and all three installs finish without a lockfile error:
   ```bash
   (cd apps/api && uv sync --frozen)
   (cd apps/web && npm ci)
   (cd tests/p03 && npm ci && npx playwright install chromium)
   ```
2. **Unit and contract checks.** Done when each command exits 0.
   ```bash
   (cd apps/api && uv run --frozen pytest)            # starts and removes its own PostgreSQL container
   (cd apps/web && npm run typecheck && npm test)
   python3 docs/contracts/p02/check_contract.py
   ```
3. **Mapped path.** Done when every printed step is `PASS` and the final line says `"ok": true`. One command checks the lockfiles, starts PostgreSQL 18, migrates, starts the API, builds and starts the web app, drives the browser at 1280px and 390px, inspects the rows with SQL, restarts the API, reopens the record in a new browser context, scans logs and the production bundle, then removes its own resources. Add `--hold-seconds 300` to keep the instance up for your own SQL. The hold blocks the shell, so start the command in the background (for example with your shell's background option) and read its output file: the `HOLD {...}` JSON line holds the `psql` command and URLs. Use a fresh run ID for every run. A repeated run ID is refused and nothing is touched.
   ```bash
   (cd apps/api && uv run --frozen python ../../scripts/p03/verify_run.py --hold-seconds 300)
   ```
   Evidence lands in `.scratch/p03/evidence/<run_id>/`. Keep it. It is untracked.
4. **Inspect the records yourself.** During the hold, run the `psql` command from the `HOLD` line. Queries are in [feature-map.md](feature-map.md#sql-checks). Compare what you see with `sql-inspection.json`. Done when the saved request text equals the text in `ui-results.json` byte for byte and the revision hash recomputes.
5. **Read the evidence.** Open `steps.json`, `ui/ui-results.json`, `ownership-drive.json`, `bundle-scan.json`, `resources-before.json` and `resources-after.json`. Look at three screenshots in `ui/screenshots/` (desktop and `mobile-390`). Done when `resources-after.json` equals `resources-before.json`. Resources labelled for another run are ignored, so a parallel labelled run is fine. An unlabelled container or volume that appears or disappears fails the step.
6. **Clean up orphans.** A crashed run can leave labelled containers. List them, remove only a stopped one by naming its run ID:
   ```bash
   python3 scripts/p03/harness.py orphans
   python3 scripts/p03/harness.py remove-orphan <run_id>
   ```
   Leave running containers and anything without the `edge-os.test=1` label alone.

## Report

State the candidate commit (`git rev-parse HEAD`), the run ID, who ran it, and each step's result. Name checks that did not run and why. A written recipe that no one executed is a draft.

## Extend

In the same change that adds a feature, add its row to [feature-map.md](feature-map.md) (UI route, API route, SQL check, evidence file), add its steps to `tests/p03/e2e.spec.mjs` and `apps/api/tests`, and run the path again.
