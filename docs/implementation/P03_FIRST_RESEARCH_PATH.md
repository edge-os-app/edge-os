# P03 first Research path

Ticket: [P03](https://github.com/edge-os-app/edge-os/issues/13). Base `eddff1a169dcf2c79cad7d9b4adb92e3dc6e3f51`. Branch `ticket/p03-first-research-saved-path`.

**Status: implementation candidate under review.** This file records what the code does and what its checks cover. It does not approve a merge, a Privy app, hosting, a real model, a wallet or any transaction. The builder accepts and merges.

A user submits a request in a browser. A FastAPI service verifies a Privy access token, saves the request and every later step in PostgreSQL, asks the one question that is needed, shows the rules for review, saves an immutable revision and reopens the same record after a restart.

## What was built

```text
apps/api/   FastAPI, SQLAlchemy 2.0, Alembic, PyJWT. src/edge_os_api, migrations, tests
apps/web/   Next.js 16 app router. Organic tokens and fonts from the P43 export. vitest tests
scripts/p03/  harness.py (isolated instances), tokens.py (test signer), verify_run.py (the mapped path)
tests/p03/  Playwright checks, desktop 1280 and mobile 390
.agents/skills/verify-edge-os/  the verification skill and feature map
```

### API routes

Every route except `/healthz` and `/readyz` needs a verified principal. The owner comes from the token. A request body never carries an owner, and any extra field at any depth returns 422.

| Route | Purpose |
|---|---|
| `GET /healthz`, `GET /readyz` | Process up. Database reachable, schema at head, key loaded. No configuration values |
| `GET /v1/me` | The verified user's internal ID |
| `GET /v1/interpreter` | Fixture label and the scripted sample requests |
| `POST /v1/research/requests` | Save the exact words, restrictions, kind and job. Interpret and route |
| `POST /v1/research/requests/{id}/clarifications` | Answer one open question against a named revision |
| `GET /v1/research/requests`, `GET /v1/research/requests/{id}` | List and reopen the whole saved record |
| `POST /v1/strategies/{id}/revisions` | Publish. Needs `operation_id`, `idempotency_key`, parent, draft and strategy |
| `GET /v1/strategies/{id}/revisions/{rev}`, `GET /v1/operations/{op}` | Exact revision and lost-acknowledgement recovery |

### Storage

PostgreSQL 18.6. Migration `0001` creates `users`, `records`, `strategy_revisions` and `idempotency_records`. A trigger rejects UPDATE and DELETE on all three record tables.

- `records` holds the P02 envelope for each record type. Composite foreign keys `(owner_id, …)` tie every link to the same owner. A unique index allows one successor per interpretation revision, so lineage cannot fork.
- `strategy_revisions` stores the exact hashed bytes. One partial unique index gives each strategy one root slot. A composite key ties a parent to the same owner and strategy.
- `idempotency_records` is keyed by `(owner_id, method, path, idempotency_key)`. It is written in the same transaction as the revision.
- After each write the service runs the frozen P02 `validate_record_bundle` over the whole lineage before commit.

### Routing and compilation

The router follows the P02 outcome rules and uses the frozen validators through `apps/api/src/edge_os_api/p02.py`. That adapter loads `docs/contracts/p02/check_contract.py` unchanged and refuses to start if any pinned P02 file hash changes.

- Restrictions that the contract cannot represent return `UNSUPPORTED` before any question. Their text is kept. (P02's example router checks them later. Early is the better user result and changes no record shape.)
- Missing, conflicting or unadopted meaning returns `NEEDS_CLARIFICATION` with one finding per field.
- `SIMULATE`, `OBSERVE_FORWARD` and `REQUEST_LIVE` return `UNSUPPORTED`. `INVESTIGATE_EFFECT` stays an investigation. With a market it returns `UNRESOLVED` because no research run exists in this build. No signal and no strategy are created.
- A strategy compiles only from adopted meaning and passes `validate_strategy`. `execution_permission` is always `NOT_GRANTED`.

### The fixture interpreter

`FixtureInterpreter` is the model-adapter boundary. It makes no model call. It answers four scripted requests (rough hunch, specific thesis, no thesis, launch-age meaning). Other text returns `INVALID_INPUT` with `interpreter_no_scripted_response`, saved as a system outcome, not a verdict on the idea. Every response carries the fixture label and the UI shows it. The market, cost and risk values are the synthetic P02 fixture values and are labelled synthetic.

### Authentication

PyJWT verifies `ES256` only, with `iss=privy.io`, `aud` equal to the configured app ID as a plain string, and required `exp`, `iat`, `iss`, `aud`, `sub`, `sid`. After verification a payload with a top-level `linked_accounts` or `custom_metadata` claim is refused. That is an Edge OS policy, not a Privy guarantee. The key is a static P-256 PEM from configuration, with an optional previous key for rotation. There is no app secret and no setting that disables authentication. Two operator log lines, `auth.signature_failure` (a spike) and `auth.previous_key_accepted` (the previous key can go), appear at most once a minute each, with a running total and no token. A test source scan fails the build if `dependency_overrides` appears under `src/`.

Web side: sign-in ends with a visible message if Privy reports an error or the person closes its window (`useLogin` `onError`). A sign-in that is slow says so after a minute and offers Try again without leaving the window. A rejected session (a 401 from the API) logs the provider out too, shows "Your session was rejected or has ended" with focus, and the next sign-in is a real one. This is covered by a unit test with a mocked bridge. Privy's real window behavior was not run. `getAccessToken` is the only token source. `createOnLogin` is `"off"` for Ethereum and Solana. The Privy module loads only when sign-in is configured. The browser harness injects a labelled test session through `window.__EDGE_OS_TEST_AUTH__` before page scripts run. The fixture provider, its token and its key live under `tests/p03` only. The product code does contain the small seam that reads `window.__EDGE_OS_TEST_AUTH__`, so the production bundle includes that reader. It only supplies a token string to the API, which verifies every token, and the app shows a visible banner when it is used. No environment variable or build flag selects it. The production bundle scan finds neither the fixture label nor any private-key block, and finds the `createOnLogin: "off"` literals.

## Versions that the locks resolved

`apps/api/uv.lock` and `apps/web/package-lock.json` are the source. Python 3.14.4, uv 0.12.16, FastAPI 0.142.2, Pydantic 2.13.5, pydantic-settings 2.15.0, Uvicorn 0.54.0, PyJWT 2.15.1, SQLAlchemy 2.0.54, Alembic 1.20.0, psycopg 3.3.6, pytest 9.1.1, httpx 0.28.1. Node 24.13.1, npm 11.8.0, Next 16.3.8, React 19.3.0, `@privy-io/react-auth` 3.47.0, TypeScript 5.9.3 (`next build` accepts it; the registry's 7.0.2 was not tried), vitest 5.0.3, Playwright 1.64.0. PostgreSQL image `postgres:18.6-trixie`, image ID `sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336` (arm64, pulled 2026-10-08). Each verification run records the exact identities in `environment.json`.

Differences from the P01 table: none in pins. Publication returns `409 parent_revision_conflict`, identical for a foreign and a random parent, as the frozen P02 text requires. The P01 row A22 says 404 for a foreign parent. The P02 contract is the more specific source, so P02 controls. TypeScript is now fixed at 5.9.3. FastAPI 0.142.2 wraps routers in an internal `_IncludedRouter`, so the route walk flattens it. Starlette's `TestClient` prints a deprecation notice for `httpx`; the pins stay as accepted.

## Run it

Use the [verification skill](../../.agents/skills/verify-edge-os/SKILL.md). Short form:

```bash
(cd apps/api && uv sync --frozen && uv run --frozen pytest)
(cd apps/web && npm ci && npm run typecheck && npm test)
(cd tests/p03 && npm ci && npx playwright install chromium)
(cd apps/api && uv run --frozen python ../../scripts/p03/verify_run.py)
```

Local development needs a PostgreSQL 18 database, `EDGE_OS_*` settings (see `apps/api/.env.example`), `alembic upgrade head`, then `uvicorn edge_os_api.main:create_app --factory`. The web app needs `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_PRIVY_APP_ID` at build time.

## What the checks prove and what they do not

Proved against a real PostgreSQL 18.6 container, a real uvicorn process and a real browser: signed fixture tokens through the production verifier (matrix rows A1–A13, A20, A24–A29), owner-scoped reads and writes, cross-owner denial on saved rows, exact original words, clarification lineage, publication idempotency and conflicts under concurrent requests, restart and reopen, the one-root-slot rule, append-only rows, startup and readiness failures, route default-deny, cleanup of only the run's own resources.

Not proved: any real Privy login or token (`R1`–`R4`), the Dashboard key type, token rotation behavior, real model output, research execution, deployment, screen readers, a physical phone, or that a first-time user understands the screens. Keyboard checks cover Tab, Shift+Tab, arrow keys, Enter and Escape on the paths in `tests/p03/e2e.spec.mjs` in Chromium only. Browser checks cover Chromium; Safari and Firefox were not run.

## Test infrastructure rules

The harness removes only what its own `Postgres` object created. Ownership is an exclusive claim, not a name or run-label match: the container is made with `docker create` (a second caller with the same name fails, so a successful create is the claim, and cleanup uses the returned container ID), and the volume carries a random per-attempt claim label that the caller must still see after the idempotent volume create. Two callers that use the same run ID at the same time therefore end with one owner, and the loser's cleanup removes nothing. A repeated run ID, a foreign container with the same name or an existing volume makes the start refuse and change nothing. `verify_run.py` also refuses an existing evidence folder, web build folder or tsconfig copy for its run ID and exits 2 before it creates or deletes anything. It then claims the build folder and the tsconfig copy by exclusive creation, so a second call with the same run ID that passes the first check still refuses, and each call removes only the paths it created. `apps/api/tests/test_harness_isolation.py` covers these cases. Orphan removal needs the run ID, a stopped container and matching labels. The cleanup comparison ignores resources that belong to another run's `edge-os.test.run` label, so a parallel run cannot cause a false failure, while any unlabelled change still shows.

## Interface checks

`tests/p03/quality.spec.mjs` runs with the end-to-end spec. It measures every visible control against the accepted 44px minimum (radios and checkboxes through their label), watches for console errors, page errors and failed requests on the main path, runs axe-core with the WCAG 2.0 to 2.2 A and AA tags on five states (an automated pass covers part of WCAG and nothing more), checks text and placeholder contrast (4.5:1, 3:1 for large text) and that long unbroken text never scrolls the page sideways, and checks that focus stays in the surface that took an answer (the main page, the desktop side panel or the modal sheet) and lands on the new state after a save. The modal sheet wraps Tab and Shift+Tab inside itself.

## Open items for the builder

- The API reads the frozen P02 contract from `docs/contracts/p02` in the repository tree at runtime (`apps/api/src/edge_os_api/p02.py`). A deployment that ships only `apps/api` would fail at import. This slice runs from the repository.

- Q1–Q4 of the P01 profile still need a Privy development app. The official Privy token pages read on 2026-10-08 (Exa fetch) still describe ES256, the claim list, `sid` in both token types and identity tokens that carry linked accounts. They name no JWKS URL for access tokens.
- Q5: the web config offers email login only, a conservative placeholder. A connected wallet is not an identity.
- Record sizes and rate limiting are not set beyond a 256 KiB body cap (enforced while streaming) and a JSON nesting limit of 100. U+0000 in any text field returns 422.
- `POST /v1/research/requests` has no idempotency key. A retry after a lost acknowledgement saves a second request. Publication has the recovery path. The list shows the 50 most recent requests and says when more exist.
- The append-only triggers assume the application database role does not own the tables and is not a superuser. The tests connect as a superuser, so they prove the trigger, not least-privilege access. `TRUNCATE` is not blocked. The web app sets no security headers (CSP, frame-ancestors).
- A database that accepts connections and never answers (a paused server) is not detected. Connect and pool timeouts cover refused and slow connects. Fault injection uses a database that refuses connections.

## Provenance

Patterns, not code, came from the read-only Assensus checkout `okx-ai-hack/assensus` at commit `02860cc5daf46d49f8b6a8ac8a524e0af7ac0b0a`: `services/api/app/auth.py` (PyJWT ES256 with static key, DID prefix check), `apps/web/lib/auth.ts` (injectable token seam, probe after sign-in, retry on 401, no stored token) and `services/api/tests/test_privy_verification_key.py` (key transport). That commit has no `LICENSE` file, so nothing was copied. Assensus does not discriminate identity tokens; this API adds the claim-presence policy. Fonts and tokens come from the supplied P43 export (Caprasimo and Figtree, SIL Open Font License).
