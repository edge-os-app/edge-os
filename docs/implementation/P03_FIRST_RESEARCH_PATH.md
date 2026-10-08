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

PyJWT verifies `ES256` only, with `iss=privy.io`, `aud` equal to the configured app ID as a plain string, and required `exp`, `iat`, `iss`, `aud`, `sub`, `sid`. After verification a payload with a top-level `linked_accounts` or `custom_metadata` claim is refused. That is an Edge OS policy, not a Privy guarantee. The key is a static P-256 PEM from configuration, with an optional previous key for rotation. There is no app secret and no setting that disables authentication. A test source scan fails the build if `dependency_overrides` appears under `src/`.

Web side: `getAccessToken` is the only token source. `createOnLogin` is `"off"` for Ethereum and Solana. The Privy module loads only when sign-in is configured. The browser harness injects a labelled test session through `window.__EDGE_OS_TEST_AUTH__` before page scripts run. The fixture provider and its token live under `tests/p03` only. No environment variable or build flag selects it. The production bundle scan finds neither the fixture label nor any key block.

## Versions that the locks resolved

`apps/api/uv.lock` and `apps/web/package-lock.json` are the source. Python 3.14.4, uv 0.12.16, FastAPI 0.142.2, Pydantic 2.13.5, pydantic-settings 2.15.0, Uvicorn 0.54.0, PyJWT 2.15.1, SQLAlchemy 2.0.54, Alembic 1.20.0, psycopg 3.3.6, pytest 9.1.1, httpx 0.28.1. Node 24.13.1, npm 11.8.0, Next 16.3.8, React 19.3.0, `@privy-io/react-auth` 3.47.0, TypeScript 5.9.3 (`next build` accepts it; the registry's 7.0.2 was not tried), vitest 5.0.3, Playwright 1.64.0. PostgreSQL image `postgres:18.6-trixie`, image ID `sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336` (arm64, pulled 2026-10-08). Each verification run records the exact identities in `environment.json`.

Differences from the P01 table: none in pins. TypeScript is now fixed at 5.9.3. FastAPI 0.142.2 wraps routers in an internal `_IncludedRouter`, so the route walk flattens it. Starlette's `TestClient` prints a deprecation notice for `httpx`; the pins stay as accepted.

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

## Open items for the builder

- Q1–Q4 of the P01 profile still need a Privy development app. The official Privy token pages read on 2026-10-08 (Exa fetch) still describe ES256, the claim list, `sid` in both token types and identity tokens that carry linked accounts. They name no JWKS URL for access tokens.
- Q5: the web config offers email login only, a conservative placeholder. A connected wallet is not an identity.
- Record sizes, list limits and rate limiting are not set beyond a 256 KiB body cap.
- A database that accepts connections and never answers (a paused server) is not detected. Connect and pool timeouts cover refused and slow connects. Fault injection uses a database that refuses connections.

## Provenance

Patterns, not code, came from the read-only Assensus checkout `okx-ai-hack/assensus` at commit `02860cc5daf46d49f8b6a8ac8a524e0af7ac0b0a`: `services/api/app/auth.py` (PyJWT ES256 with static key, DID prefix check), `apps/web/lib/auth.ts` (injectable token seam, probe after sign-in, retry on 401, no stored token) and `services/api/tests/test_privy_verification_key.py` (key transport). That commit has no `LICENSE` file, so nothing was copied. Assensus does not discriminate identity tokens; this API adds the claim-presence policy. Fonts and tokens come from the supplied P43 export (Caprasimo and Figtree, SIL Open Font License).
