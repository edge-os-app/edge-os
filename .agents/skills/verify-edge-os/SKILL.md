---
name: verify-edge-os
description: Verify Edge OS end to end on a fresh isolated instance. Use after a feature change, before claiming a runtime slice done, when repeating another agent's verification, or when inspecting saved records, evidence and cleanup.
---

# Verify Edge OS

Run the mapped path on a fresh instance, read the saved records yourself, keep the evidence, clean up only what the run created. [feature-map.md](feature-map.md) lists each feature, its UI route, API route, SQL check and evidence file. Fixtures stay fixtures: a pass here proves no real model, no real Privy login, no research run and no wallet, deposit, transaction or removal behavior at any provider. The P05 phase runs the actual pinned Hermes against a local fake provider that returns authored text; it proves the runtime wiring, never how a real model reads a request.

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
   (cd apps/api && P05_EVIDENCE_DIR=<private folder> uv run --frozen pytest ../../tests/hermes_interpretation)   # actual pinned Hermes in a no-network container; builds and removes its own image
   ```
   The pinned Hermes checkout must exist at `/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent`, in the workspace root above `edge-os/` and outside this repository (commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba`, no modified tracked file). The image build needs network access once.
3. **Mapped path.** Done when every printed step is `PASS` and the final line says `"ok": true`. One command checks the lockfiles, starts PostgreSQL 18, migrates, starts the API, builds and starts the web app, drives the browser at 1280px and 390px, inspects the rows with SQL, restarts the API, reopens the record in a new browser context, then runs the P05 phase, scans logs and the production bundle, and removes its own resources. Before the restart it also runs the #58 connected financial phase (`scripts/p03/financial_phase.py`): fixture execution ports, the bounded worker process, `financial-journey.spec.mjs`, SQL against the financial schemas and the run-owned `fixture-effects.jsonl`; after the restart it restarts the worker and drives `financial-restart.spec.mjs`. It also runs the #58 recorded-history research phase (`scripts/p03/research_phase.py`): SYNTHETIC recorded responses only, `research-history-journey.spec.mjs` with no worker, a killed-worker fault injection, one research worker pass, `research-history-report.spec.mjs` (reports, source loss, market adoption, publication and labelled history replay) and SQL; after the restart, another worker pass and `research-history-restart.spec.mjs`. `--actual-data PACKET` is an explicit opt-in that refuses before anything starts while no approved packet and no actual adapter exist. The P05 phase builds the pinned Hermes image, replaces the API with `scripts/hermes_interpretation/serve_local.py` on the same port and database, drives `tests/p03/interpreter.spec.mjs`, compares the saved attempt rows with HTTP, denies another owner, restarts and reopens with `interpreter-after-restart.spec.mjs`, then starts the standard API again. `--skip-p05` leaves the phase out and `--only-p05` leaves out everything before it; both are development shortcuts and neither is a full pass. Add `--hold-seconds 300` to keep the instance up for your own SQL. The hold blocks the shell, so start the command in the background (for example with your shell's background option) and read its output file: the `HOLD {...}` JSON line holds the `psql` command and URLs. Use a fresh run ID for every run (`--run-id` takes 4 to 24 lowercase letters or digits; the default is generated). Keep the evidence outside a disposable clone with `--evidence-root <folder>`. A repeated run ID is refused and nothing is touched.
   ```bash
   mkdir -p .scratch/p03
   RID=p03$(openssl rand -hex 4); LOG=.scratch/p03/verify-$RID.log    # a log per run, so an old final line never matches
   (cd apps/api && uv run --frozen python ../../scripts/p03/verify_run.py --run-id $RID --hold-seconds 300 > ../../$LOG 2>&1 &)
   timeout 900 sh -c "until grep -qE '^(HOLD|REFUSED|[{])' $LOG; do sleep 5; done"
   tail -n 5 $LOG   # a HOLD line holds the psql command and URLs
   ```
   The wait ends at the `HOLD` line, at a `REFUSED` line, or at the final JSON line. A run that fails before the hold prints the final JSON line with `"ok": false`. If the last lines show no `HOLD`, the run did not reach the hold: read `steps.json` and stop. After the hold, wait for the final JSON line with `timeout 900 sh -c "until grep -q '^[{]' $LOG; do sleep 5; done"` and read `"ok"` and the run ID from it; step 5 needs that. `timeout` is not on stock macOS (Homebrew coreutils has it); if it is missing, use your shell's own bounded wait. Some agent shells kill a background job when the call ends. Then start the command with the tool's own background option. A killed run leaves its labelled container and volume running: list them with `python3 scripts/p03/harness.py orphans`, stop only the container that carries your run ID with `docker stop edge-os-test-pg-$RID`, then remove it as step 6 says.
   Python 3.14 and Node 24 are required. The harness picks free loopback ports itself.
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
