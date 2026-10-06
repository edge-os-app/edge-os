# P01 application, authentication and storage profile

Ticket: [P01](https://github.com/edge-os-app/edge-os/issues/6). Prepared 2026-10-06 against base `010c465395f529d95808dfbe39080ca0e803c339`.

**Status: proposed profile. Nothing in this file has run.** Every command is marked `UNEXECUTED`. P03 ([#13](https://github.com/edge-os-app/edge-os/issues/13)) implements this profile and runs its checks. This file does not approve dependency installation, a Privy app, hosting, wallet creation, signing, funding or any transaction. It does not claim that authentication, migrations, persistence or provider integration work.

[ADR 0008](../adr/0008-python-api-postgresql-nextjs-privy-auth.md) fixes the stack: Python/FastAPI, PostgreSQL, Next.js and Privy. This profile selects the details inside that stack.

## Summary

1. The browser calls `getAccessToken()` for each API request and sends the result as `Authorization: Bearer <token>`. FastAPI verifies it. The design uses no cookie and no dev bypass.
2. FastAPI verifies the Privy access token with PyJWT. It accepts only `ES256`. It requires `exp`, `iat`, `iss`, `aud`, `sub` and `sid`. It checks `iss == "privy.io"` and requires `aud` to be the configured Privy app ID as a plain string. After signature and required-claim checks, an Edge OS policy rejects any payload that contains a top-level `linked_accounts` or `custom_metadata` claim. The policy aims to keep Privy identity tokens out. `sid` is only a required claim-shape check and does not separate token classes.
3. The verification key is a static PEM from configuration (Privy Dashboard, "Verify with key instead"). The official docs pages name no JWKS endpoint and no rotation overlap. Public SDK source suggests a per-app JWKS endpoint, which this profile does not adopt. Rotation is a manual two-key procedure (see [Key retrieval and rotation](#key-retrieval-and-rotation)).
4. The verified `sub` (a Privy DID) maps to an internal `users.id`. Every owner-scoped query takes that internal ID from the verified principal. A request body never supplies an owner.
5. Storage is PostgreSQL 18 through SQLAlchemy 2.0 (sync) with psycopg 3. Alembic applies schema changes in a separate step before the API starts.
6. Tests run against a separate Postgres container, database, OS-assigned ports and test key. Cleanup touches only resources the run created, found by run label and exact name.
7. The API never holds a Privy app secret. Login creates a `users` row and nothing else. It creates no wallet, signer, mandate or transaction.

## Decision table

"Verify" names the check P03 must run. Rows D6 and D15 are *proposed* to P02. Every row still needs the builder's confirmation when this change merges. Open items are in [Remaining bounded questions](#remaining-bounded-questions).

| # | Choice | Reason | Source | Consumer | Verification requirement |
|---|---|---|---|---|---|
| D1 | Python 3.14 (`>=3.14,<3.15`), managed with `uv` and a committed `uv.lock` | Local 3.14.4 and `uv` 0.12.16 exist. Each pinned package except `httpx` lists 3.14 in its PyPI classifiers (2026-10-06). `httpx` is pure Python and lists no 3.14 classifier. No interpreter install needed for the first slice | PyPI JSON, accessed 2026-10-06 | P03 | Lock resolves on 3.14. Test suite runs on 3.14. If a wheel is missing, fall back to 3.13 and record why |
| D2 | FastAPI 0.142.2 with Pydantic 2.13.5, pydantic-settings 2.15.0, Uvicorn 0.54.0 | Accepted stack. Current stable releases | PyPI; Context7 `/websites/fastapi_tiangolo` | P03 | T13: the lock result matches or P03 records the new pins |
| D3 | Token verification with PyJWT 2.15.1 (`pyjwt[crypto]`), `ES256` only | Privy documents ES256 tokens and third-party libraries. Its Python SDK docs show no verify method. A small PyJWT verifier avoids the Privy app secret | Privy access-tokens page; Context7 `/jpadilla/pyjwt`; Privy Python setup page; `@privy-io/node` source | P03 | Failure matrix rows A1-A13, A20 and A24-A29 pass with signed test tokens. Real-token check R1 passes when the builder authorizes a Privy app (Q1). See [Evidence classes](#evidence-classes) |
| D4 | Static verification key from configuration, up to two keys (current, previous) | Docs describe the Dashboard key. The docs pages publish no JWKS URL and no rotation rule. SDK source suggests a per-app JWKS endpoint, but it is undocumented and not adopted. Two keys avoid a forced logout during rotation | Privy access-tokens and "Optimize your setup" pages; `@privy-io/node` source | P03, operator | Startup rejects a missing or non-P-256 key. Row A20. R2 when the builder authorizes a Privy app (Q1) |
| D5 | Token delivery: `Authorization: Bearer` header, browser to FastAPI directly, explicit CORS allow-list | Privy's default local-storage mode uses this header. Cookie mode needs a custom domain and adds CSRF handling. A proxy hop adds a failure point for streams | Privy access-tokens page; Next.js docs v16.2.9 | P03, P43 | T9: allowed origin passes, other origin gets no CORS headers, no `*` |
| D6 | *Proposed.* Ownership: internal `users.id` UUID, created on first verified request from the Privy DID in `sub` | Verified identity must derive ownership. An internal ID keeps P02 records independent of the provider | ADR 0008; spec "Records and durable identity" | P02, P03 | Cross-owner cases A15-A19 and A22-A23. T3 |
| D7 | SQLAlchemy 2.0.54 (sync ORM) + psycopg 3.3.6 (`postgresql+psycopg://`) | Smallest typed access layer that Alembic can check. Sync endpoints run in FastAPI's threadpool. psycopg 3 also supports async later without a driver change | Context7 `/websites/sqlalchemy_en_20`; PyPI | P02, P03 | Request-to-record test T1 |
| D8 | Alembic 1.20.0, run explicitly before the API starts. No auto-migrate at startup | A separate step keeps schema change visible and repeatable. The API refuses to start on a revision mismatch | Context7 `/websites/alembic_sqlalchemy` | P03, deploy | M1-M4 below. T11 |
| D9 | PostgreSQL 18.6 (`postgres:18.6-trixie`, pin digest at first pull) | Current stable major. PostgreSQL 19 is beta on Docker Hub (`19beta4`) | Docker Hub tags API, 2026-10-06 | P03, deploy | `SHOW server_version` recorded in evidence |
| D10 | Next.js 16.3.8, React 19.3.0, Node 24.x, `npm` with `package-lock.json` | Local Node 24.13.1 and npm 11.8.0 exist. Next requires Node `>=20.9.0`. npm needs no extra tool | npm registry, 2026-10-06; Context7 `/vercel/next.js` v16.2.9 | P03, P43 | T13: `npm ci` and `next build` pass in P03 |
| D11 | `@privy-io/react-auth` 3.47.0 with `embeddedWallets.ethereum.createOnLogin: "off"` set explicitly | Login must create no wallet. The docs list `off` as the default. Setting it explicitly makes the intent testable | Privy "Automatic wallet creation" page | P03, P43 | T12 checks the config value only. R3 observes real Privy behavior when the builder authorizes a Privy app (Q1) |
| D12 | Styling: keep exported CSS tokens as plain CSS variables. Add Tailwind (4.3.3 on 2026-10-06) only if the P43 export needs it | ADR 0008 and the spec leave this to the actual export. P01 has no export to judge | ADR 0008; spec "Accepted application stack" | P03, P43 | P03 records the choice with the export it translated |
| D13 | No Privy app secret in the API. No dev-auth bypass flag | Token verification needs the app ID and a public key only. The secret grants server API power that login must not have | Privy docs; reference package pattern 3 | P03 | T8: `PRIVY_APP_SECRET` is not a setting. T4: no auth-disabling flag |
| D14 | Test isolation: dedicated Postgres container, per-run database, per-run volume, OS-assigned ports, test-only signing key | Cleanup must touch only test state. Fixture keys must never be trusted by a real process | FastAPI testing-dependencies docs; reference cases | P03 | T2, T6 |
| D15 | *Proposed.* Error taxonomy: 401 `auth_required` / `auth_invalid` / `auth_expired`; 503 `auth_unavailable` (verifier cannot run) and `service_unavailable` (database); 422 `validation_error`; 404 for another owner's record | Lets the client refresh once on expiry. Hides record existence. Separates operator failure from bad input | Reference input; Privy "tokens" page | P02 (error shape), P03 | Failure matrix |
| D16 | Verification skill and its feature map are P03's deliverable | Issue #6 and the reference map assign it to P03 | Issue #6; reference map | P03 | Not part of P01 |

## Pinned versions

Values come from PyPI, the npm registry and Docker Hub on 2026-10-06. These registries move. P03 records the versions its lockfiles actually resolve and updates this table in the same PR if they differ.

| Component | Pin | Note |
|---|---|---|
| Python | 3.14.x | Local interpreter 3.14.4 |
| uv | `>=0.12.16` | Tool, not a dependency |
| fastapi | 0.142.2 | Pulls Starlette (latest 1.7.0) |
| uvicorn | 0.54.0 | Plain package, no `[standard]` extra |
| pydantic / pydantic-settings | 2.13.5 / 2.15.0 | |
| pyjwt[crypto] | 2.15.1 | `cryptography` resolved by the lock (latest 50.0.2) |
| SQLAlchemy | 2.0.54 | See note below |
| alembic | 1.20.0 | Requires `SQLAlchemy>=2.0` |
| psycopg[binary] | 3.3.6 | Binary wheel for local runs. A production image may build from source (bounded question) |
| pytest, httpx | 9.1.1, 0.28.1 | httpx backs FastAPI's `TestClient` |
| PostgreSQL | 18.6 | Image `postgres:18.6-trixie`, index digest `sha256:fc973eb97c9fd04bfa1840e0f510719a584ccb3be8debfe6a4144637a9dfe8cf` (Docker Hub, 2026-10-06 07:11Z) |
| Node / npm | 24.x / 11.x | Local 24.13.1 / 11.8.0 |
| next / react / react-dom | 16.3.8 / 19.3.0 / 19.3.0 | Context7 holds Next docs for v16.2.9, one minor behind |
| @privy-io/react-auth | 3.47.0 | Peers: `react ^18 \|\| ^19` |
| TypeScript | Version that `next build` accepts | Registry shows 7.0.2. P01 did not check its Next compatibility |

**SQLAlchemy note.** The 2.1 line reached stable on 2026-09-24 (2.1.0), 12 days before this profile. It changes named-type handling and autoflush. This stack needs no 2.1 feature. The 2.1 migration page that Exa returned still labels itself a release candidate, so it is stale. Pin 2.0.54, whose docs Context7 holds. Revisit after a measured need.

## Application layout (proposed)

```text
apps/api/   pyproject.toml, uv.lock, src/edge_os_api/, migrations/, tests/
apps/web/   package.json, package-lock.json, app/
```

P03 may adjust names. It must keep two separate toolchains and no shared lockfile.

## Configuration

The API reads typed settings with pydantic-settings, prefix `EDGE_OS_`. A missing required value stops startup with a message that names the field and never prints its value. `.env` files stay untracked. The repository `.gitignore` already ignores `.env` and `.env.*` and allows `.env.example`. Commit names only in `.env.example`.

| Variable | Required | Rule |
|---|---|---|
| `EDGE_OS_ENV` | yes | `local`, `test` or `production`. No default |
| `EDGE_OS_DATABASE_URL` | yes | Secret. Must start `postgresql+psycopg://`. In `test`, host must be `127.0.0.1` or `localhost` and database name must start `edge_os_test_` |
| `EDGE_OS_PRIVY_APP_ID` | yes | Non-empty string. Used as expected `aud` |
| `EDGE_OS_PRIVY_VERIFICATION_KEY` | yes | PEM public key. A literal `\n` converts to a newline. Must load as an EC P-256 key at startup |
| `EDGE_OS_PRIVY_VERIFICATION_KEY_PREVIOUS` | no | Same rules. Used only during rotation |
| `EDGE_OS_CORS_ALLOWED_ORIGINS` | yes | Explicit list. `*` is invalid. In `production`, each origin must be `https://` |
| `EDGE_OS_BUILD_SHA` | no | Falls back to `git rev-parse HEAD` in local runs, else `unknown` |

Web variables: `NEXT_PUBLIC_PRIVY_APP_ID` and `NEXT_PUBLIC_API_BASE_URL`. Next.js inlines `NEXT_PUBLIC_*` values at build time, so they are public. Put no secret in them. The web app needs no Privy secret.

## Ports (local and test)

| Service | Dev | Test |
|---|---|---|
| Web | 3000 | Free loopback port, chosen by the harness |
| API | 8000 | Free loopback port, chosen by the harness |
| Postgres (loopback only) | 15432 | Docker-assigned loopback port (`docker port` reports it) |

Test runs use no fixed port, so parallel lanes cannot collide. A busy dev port stops the run. A run never kills a process it did not start and never reuses a database it did not create.

## Startup, health and build identity

**Startup sequence (the API process).** Load settings. Load the verification key(s). Connect to Postgres. Read the Alembic revision. Compare it with the script head. Any failure exits non-zero with a plain message. This runs in the FastAPI lifespan handler.

**Health endpoints (no authentication, no secrets):**

| Route | Meaning | Body |
|---|---|---|
| `GET /healthz` | Process is up. No database call | `status`, `build_sha`, `started_at` |
| `GET /readyz` | Database reachable, revision equals head, key loaded | `status`, `schema_revision` |

`/readyz` returns 503 when any check fails. These routes expose no key, URL, app ID or user data.

## Recipes (all UNEXECUTED)

Commands assume the proposed layout. P03 corrects paths and exercises each one.

**Local startup (dev):**

```bash
# UNEXECUTED
docker run -d --name edge-os-dev-pg --label edge-os.dev=1 \
  -e POSTGRES_PASSWORD=<dev-password> -p 127.0.0.1:15432:5432 \
  -v edge-os-dev-pg:/var/lib/postgresql postgres:18.6-trixie
cd apps/api && uv sync --frozen
uv run alembic upgrade head                       # migration step
uv run uvicorn edge_os_api.main:app --host 127.0.0.1 --port 8000
cd ../web && npm ci && npm run dev -- --hostname 127.0.0.1 --port 3000
```

The volume path above follows the official image's PostgreSQL 18 layout. P03 confirms it against the image documentation before use.

**Migration checks:**

| ID | Check (UNEXECUTED) | Pass condition |
|---|---|---|
| M1 | `alembic upgrade head` on an empty test database | Exit 0. Revision equals script head |
| M2 | `alembic check` after M1 | "No new upgrade operations detected" (models and migrations agree) |
| M3 | Start the API against an empty (unmigrated) database | Process exits non-zero with a revision-mismatch message |
| M4 | Once a second revision exists: build the database at revision N-1, insert rows, upgrade to head | Rows survive. Constraints hold |

Policy: forward-only migrations for the MVP. No downgrade is promised. A new migration ships with its model change in one PR.

## Authentication

### Token delivery

1. The browser holds the Privy session. Privy's SDK stores the refresh token. Application code never reads it.
2. For each API call, a single injected function `getAuthHeaders()` calls `getAccessToken()` from `usePrivy()`. The SDK refreshes a token near expiry.
3. The client sends `Authorization: Bearer <access token>` to `NEXT_PUBLIC_API_BASE_URL` only.
4. On `401 auth_expired`, the client calls `getAccessToken()` and retries once. On any other 401 it shows the sign-in state.
5. The client never sends the identity token and never puts a token in a URL.

Consequences for other tickets:

- Next.js server components cannot read the token (local-storage mode). Owner-scoped data loads in client components.
- Browser `EventSource` cannot set headers. A stream endpoint needs `fetch` streaming with the header, not a query-string token. Privy's token guide forbids tokens in URLs.
- Privy's guide says to use HTTPS. `http://localhost` for local development is this profile's judgment, not a Privy statement.

### Verifier profile

PyJWT `decode` with these settings:

| Setting | Value |
|---|---|
| `algorithms` | `["ES256"]` only |
| Key | Preloaded EC P-256 public key object(s) |
| `issuer` | `"privy.io"` |
| `audience` | `EDGE_OS_PRIVY_APP_ID` |
| `options.require` | `["exp", "iat", "iss", "aud", "sub", "sid"]` |
| `leeway` | 10 seconds, a code constant |
| Signature | Verified before any claim is read |

After decode, the verifier also requires `exp` and `iat` to be an `int` or `float` and not a `bool` (PyJWT converts a numeric string or a bool with `int()` and would accept it), requires `aud` to be a string equal to the app ID (PyJWT alone accepts a list that contains it) and `sub` to be a string starting `did:privy:` and at most 255 characters. The `did:privy:` prefix and length cap come from the DID examples in the docs, not from a stated rule. It rejects a token longer than 4096 characters before parsing. It does not check the `typ` header.

**`sid` and the identity-data policy.** The verifier requires `sid` to be a non-empty string of at most 255 characters. This is a claim-shape check only. `sid` does not tell an access token from an identity token, because Privy's Tokens page says the `sid` claim is present in both. The 255-character cap is this profile's choice, not a sourced limit.

A Privy identity token is signed by the same key and shares the issuer, app audience, subject, session and time claims with an access token. Its default lifetime is 10 hours, against 1 hour for an access token, and it carries linked-account data. So the API applies an explicit **Edge OS application policy**. After signature and required-claim verification, it rejects any payload that contains a top-level `linked_accounts` or `custom_metadata` claim. The rule rejects by claim presence, including an empty, null or any other value type. The policy is informed by the identity-token claims that Privy documents. It does not guarantee that the API recognizes every Privy identity token. A token that carries neither claim passes the policy. `typ: JWT` cannot discriminate, because the SDK applies it to both token types. Identity tokens are off unless the Dashboard enables them, but the API applies the policy anyway, because a client can send any credential directly to FastAPI. The policy rests on documents and SDK excerpts, not on a real-token test. R1 and R4 are the real-token checks. Both are unperformed and need separate builder authority.

Privy's docs list these claims: `sid`, `sub` (Privy DID), `iss` (`privy.io`), `aud` (app ID), `iat`, `exp` (generally 1 hour after issue). The default lifetime is configurable in the Dashboard.

Exception mapping. The `try` block wraps only the `jwt.decode` call and the post-decode checks. Database errors never map to an auth code.

- `ExpiredSignatureError` gives `auth_expired`.
- `jwt.InvalidKeyError` gives `auth_unavailable`. It describes the key, not the token. Startup loading makes it unreachable in normal operation.
- Every other exception from decode gives `auth_invalid`. This includes `InvalidTokenError` subclasses and any unexpected exception type. A non-`InvalidTokenError` exception also logs `auth.verifier_error` with the exception class name only, at most once per minute per class, because an attacker chooses the input.
- Before decode, a verifier or key list missing from application state gives `auth_unavailable`.
- The log never contains the token.

PyJWT checks the signature before claims, so an expired token with a bad signature gives `auth_invalid`. A validly signed token with several claim defects gets the code of PyJWT's first failing check. PyJWT 2.15.1 checks `iat`, `nbf`, `exp`, `iss`, `aud` and `sub` in that order, so a token with a future `iat` and an expired `exp` gives `auth_invalid`. Tests assert single-defect rows only. An `iat` more than 10 seconds in the future gives `auth_invalid`, so the API host clock must stay within 10 seconds of Privy's. P03 confirms each PyJWT behavior above by test; P01 ran none.

### Key retrieval and rotation

What the official docs say, and what they do not:

- Documented: the key comes from the Dashboard (Configuration > App settings, "Verify with key instead"). The Node SDK otherwise fetches it from Privy's API and caches it. After a rotation, a copied key must be updated by hand.
- Not documented on the pages P01 read: a JWKS URL for Privy-issued tokens, a `kid` header, whether the old key stays valid after rotation. The JWKS pages describe a custom auth provider's keys that Privy fetches.
- Inconsistent in the docs: the key is called "Ed25519", while the token algorithm is ES256 and the JS example calls `importSPKI(key, "ES256")`. Ed25519 and ES256 (ECDSA P-256) are different. P03 must load the real Dashboard key and confirm its type. The startup check rejects any key that is not EC P-256.

Package-source evidence (not documentation pages). The official `@privy-io/node` SDK source, read as search excerpts on unpkg (0.28.0) and jsDelivr (0.34.0) on 2026-10-06, shows:

- It fixes `ES256` and issuer `privy.io`, checks `typ: 'JWT'` and sets `audience` to the app ID.
- It imports a supplied key with `importSPKI(key, 'ES256')`. That implies an SPKI EC P-256 key, so "Ed25519" in the docs is probably an error.
- It requires a string `sid` and `sub` and numeric `iat` and `exp`.
- Without a supplied key it builds a JWKS URL `${apiUrl}/v1/apps/${appId}/jwks.json` with a 60-minute cache and a 10-minute cooldown. The excerpts do not show the default `apiUrl`.
- Its type notes say a verification key or a JWKS endpoint is available in the Dashboard.

P01 read excerpts, not the full package. The version labels disagree: excerpts exist for 0.28.0 and 0.34.0, and one unpkg `@latest` lookup returned 0.16.0. Current SDK behavior is therefore unconfirmed. Treat this as a lead for Q2 and Q3, not as a documented contract.

Chosen mechanism: static key(s) from configuration. No runtime key fetch, so key retrieval cannot fail per request. A JWKS fetch is a possible later change (see below).

Rotation procedure (UNEXECUTED, operator):

1. Rotate the key in the Privy Dashboard.
2. Set `EDGE_OS_PRIVY_VERIFICATION_KEY_PREVIOUS` to the old key and `EDGE_OS_PRIVY_VERIFICATION_KEY` to the new key. Restart the API.
3. The verifier tries the current key, then the previous key. Only a signature failure moves to the next key.
4. After the configured access-token lifetime has passed (1 hour by default), remove the previous key. Restart.

Risk: if the Dashboard invalidates the old key at once, tokens signed by it fail until clients refresh. If an operator forgets step 2, every login fails with `auth_invalid`. P03 adds two log counters: `auth.signature_failure`, so an operator can see a spike, and `auth.previous_key_accepted`, so an operator can see when removing the previous key is safe. The previous key has no automatic expiry.

If P03 confirms the JWKS endpoint against a real app (Q3), a cached JWKS fetch can replace the static key in a new decision. Do not use an unconfirmed URL.

### Logout limit

The API keeps no session. A token stays valid until `exp` after logout. Login is not financial authority, so this does not touch the wallet or mandate boundary ([ADR 0002](../adr/0002-separate-evidence-and-financial-authority.md), [ADR 0005](../adr/0005-model-and-execution-authority-boundary.md)). A shorter token lifetime is a Dashboard setting and a builder choice.

### Login creates no authority

- The web config sets `createOnLogin: "off"` explicitly (D11).
- The API holds no app secret (D13) and has no route that creates a wallet.
- The only write caused by login is the first-seen `users` row.
- A later ticket that creates a wallet needs its own explicit user action and builder authority.

## Ownership

Interface proposed to P02. P02 owns the machine records. This ticket edits no P02 contract.

```text
Principal:   user_id (internal UUID)   privy_did (string, from verified sub)
users:       id UUID PK | privy_did text UNIQUE NOT NULL | created_at timestamptz
Owned table: owner_id UUID NOT NULL REFERENCES users(id) + index on owner_id
```

Rules:

1. A FastAPI dependency `require_principal` verifies the token, then runs `INSERT ... ON CONFLICT (privy_did) DO NOTHING` and selects the row. Two first requests from one user create one row.
2. Repository functions take a `Principal`. They add `WHERE owner_id = :principal.user_id` to every read, update and delete. They set `owner_id` from the principal on every insert.
3. Every request model inherits one base model with `extra="forbid"`. This covers nested models and partial-update bodies. A body that carries `owner_id` at any depth returns 422 and changes nothing. No code reads an owner from a body, query string or header.
4. A record owned by someone else returns 404, the same response as a missing record. A denied mutation changes no row.
5. Every route except `/healthz` and `/readyz` carries `require_principal`. Default deny. Router-level dependencies do not cover `/docs`, `/openapi.json`, `/redoc`, mounted sub-apps or WebSocket routes. Outside `EDGE_OS_ENV=local`, the app disables the docs routes. T4 walks mounts and WebSocket routes too.
6. A connected wallet address is not an identity. Only the verified `sub` identifies a user.
7. References. A record that points to another owned record stores `owner_id` and the parent ID. A composite foreign key `(owner_id, parent_id)` references the parent's `(owner_id, id)`. For every insert or update that sets a parent ID, the repository looks the parent up under the principal's scope first and returns 404 when it is missing. A foreign-key violation (SQLSTATE 23503) raised by such an insert or update maps to the same 404 body and never to 500 or 409. A delete blocked by the caller's own dependent records returns 409 about the caller's own record, which leaks nothing. Another owner's parent ID and a random ID give the same 404.
8. Uniqueness. Every unique constraint on a value a user can choose or supply (natural key, idempotency key, canonical hash) includes `owner_id`. Two owners can hold the same value as separate rows. A global constraint would return 409 to a second owner and reveal that the first owner's value exists. If P02 needs a shared immutable record, P02 defines it as an explicit exception (Q8).
9. Background work. A worker takes `owner_id` from the persisted job row that the API wrote under a verified principal. It never takes an owner from a message body, a token or a request field. The worker's design is a later ticket. This rule fixes the boundary.

Not chosen: PostgreSQL row-level security. It would add a second layer, but also session-variable plumbing. Add it only if the builder wants defense in depth (bounded question Q6).

## Test boundary

The test boundary is an authenticated application request, then persisted records, then retrieval. Issue #6 records that the builder accepted this boundary. The spec's Testing Decisions section still calls the seam unconfirmed. That spec text is stale, so P01 follows the issue. A browser check confirms the UI reads and acts on those same records. Pure calculation and compiler tests stay separate and are not authentication evidence.

### Isolated instance (proposed, UNEXECUTED)

| Item | Rule |
|---|---|
| Database server | Container `edge-os-test-pg-<run_id>`, image `postgres:18.6-trixie`, labels `edge-os.test=1` and `edge-os.test.run=<run_id>`, published as `127.0.0.1::5432` (Docker picks the host port) |
| Data volume | Explicit named volume `edge-os-test-pg-<run_id>` created with the same labels and mounted at `/var/lib/postgresql`. The run never relies on the image's anonymous volume |
| Database | One database per run, named `edge_os_test_<run_id>` |
| API | Uvicorn on `127.0.0.1` at a free port chosen by the harness. The harness starts the server process itself (not through a wrapper such as `uv run`) in its own process group and keeps that handle |
| Web (browser checks only) | Free loopback port chosen by the harness |
| Config | The harness builds the child's environment from scratch. It ignores ambient `EDGE_OS_*` variables and any `.env` file and builds its own database URL. `EDGE_OS_ENV=test`. Test app ID `edge-os-test-app`. Test signing key generated in memory per session. Its public half is the only key the test API trusts |
| Guard | Before any DDL or `DROP`, the harness runs `SELECT current_database()` and asserts it equals `edge_os_test_<run_id>`. It asserts the container's labels with `docker inspect`. Settings also refuse a non-loopback host or another database name in `test` |
| Cleanup | Stop only that process group through the harness's handle, after checking that the child has not already exited (`poll()`), so a reused group ID is never signalled. There is no PID file and no signal to a PID read from disk. Run `docker rm -f -v` on the container, then `docker volume rm` on the volume, each found by this run's label and exact name. Drop only this run's database. Keep the evidence directory |
| Cleanup on failure | Same steps in a `finally` or fixture teardown. A failed run still cleans its own state and still keeps evidence |
| Orphans | A crashed run can leave labeled resources. An orphan report lists resources with `edge-os.test=1` whose run ID differs from the current run, with container state and start time. Removing one needs explicit confirmation naming its run ID, and is refused while its container is running (it may belong to a live sibling run). No label-wide force removal |

Any label mismatch, an unexpected existing database or a failed guard stops the run. Cleanup never matches on name patterns alone.

### Deterministic auth fixtures

- The fixture signs tokens with a per-session test P-256 key. It sets explicit `iss`, `aud`, `sub`, `sid`, `iat` and `exp` relative to the current time. A valid access-shaped fixture carries neither `linked_accounts` nor `custom_metadata`. It runs through the production verifier. It does not use a fake verifier.
- Fixed identities: owner A `did:privy:test-owner-a`, owner B `did:privy:test-owner-b`.
- No private key is committed. The tests never read a real token or a real Dashboard key.
- The settings loader rejects the app ID `edge-os-test-app` when `EDGE_OS_ENV=production`. T10 checks this. A process trusts only the key in its configuration, so a test key cannot authenticate against a real deployment.

### Evidence classes

| Class | What it proves | What it does not prove | Where it is allowed |
|---|---|---|---|
| **Mocked auth** (`app.dependency_overrides` replaces `require_principal`) | Route wiring and owner scoping given a principal | Any signature, claim or Privy behavior | Test code only. A source check fails the build if `dependency_overrides` appears under `src/` |
| **Fixture-signed token** (real verifier, test key) | Our verifier code rejects and accepts the right inputs | That Privy's real tokens match our assumptions | Tests only |
| **Mocked web auth** (browser test injects a token provider that returns a fixture-signed token) | That the UI and API read the same records through the test API | Any Privy login, `getAccessToken()` or wallet behavior | Test harness only. The harness injects the provider at run time (for example a Playwright init script). No `NEXT_PUBLIC_*` variable or build flag selects it. The production entry point wires Privy's `getAccessToken` (T12) |
| **Real provider** (token from a real Privy app, verified with its Dashboard key) | Real claims, algorithm, key type and app binding | Production hosting, rotation behavior | Only with builder authority for a Privy app. Not available to P01 |

Real-provider checks, all needing builder authority and all UNEXECUTED:

- **R1.** Run the web and API on a non-test instance (`EDGE_OS_ENV=local`, the real app ID and Dashboard key). Log in through the browser on a builder-authorized Privy development app and make an API call that returns the owner's records. Verify the resulting access token with the configured Dashboard key through the same verifier. Record only metadata: `alg`, `iss`, `aud` equals app ID, `sub` hashed, `sid` present with its type and length, `sub` length, whether top-level `linked_accounts` or `custom_metadata` appear (the policy needs both absent from a real access token), `exp - iat`, key type and curve. Never record the token.
- **R2.** If the Dashboard offers rotation on that app: rotate, run the two-key procedure, confirm old and new tokens behave as designed. Record what Privy actually did.
- **R3.** Confirm a first login leaves the Privy user with no embedded wallet. This is the only check that observes Privy's wallet behavior.
- **R4.** If identity tokens are enabled in the Dashboard (a separate Dashboard setting and builder choice), send a real identity token for the same app to the API and record the result. The policy returns 401 only if the token carries `linked_accounts` or `custom_metadata`. A real identity token that carries neither would pass, and R4 then records that gap. If identity tokens stay disabled, record that R4 was not run. Rows A26 and A28 are then the only evidence for the policy, and they do not show that real identity tokens are rejected.

Until R1 passes, the claim is "verifier correct against fixtures." It is not "Privy integration works."

### What P03 must execute

This list is the minimum. Every check is UNEXECUTED.

| ID | Check |
|---|---|
| T1 | Request-to-record: owner A creates a record through the API. Read the row directly in Postgres. Retrieve through the API. Compare |
| T2 | Restart: stop the test API child, start it again on the same test database, read A's record as A, confirm B is denied |
| T3 | Concurrency: release N concurrent first requests (N at least 8) for one new DID behind a barrier. Repeat for at least 20 fresh DIDs, because a select-then-insert race window is short. Assert every response is 2xx, every response returns the same `user_id`, and exactly one `users` row exists per DID. Sequential calls do not count. A plain insert without conflict handling must fail this check |
| T4 | Route walk, including mounts and WebSocket routes: every non-allowlisted route has `require_principal`. No `dependency_overrides` under `src/`. No setting or code path disables auth. Docs routes are absent outside `local` |
| T5 | Log capture: run the full failure matrix. The captured logs contain no token substring |
| T6 | Cleanup: list containers, volumes and databases before and after. Nothing carrying this run's label or name remains. Every unrelated resource is unchanged. Repeat after a forced failure |
| T7 | Settings: each missing or invalid variable stops startup with a field name and no value |
| T8 | Config: the Privy app secret is not a recognized setting |
| T9 | CORS: an allowed origin gets CORS headers, another origin gets none, `*` is rejected |
| T10 | Production settings reject `edge-os-test-app` and `http://` CORS origins |
| T11 | Health: `/healthz` returns no configuration values. After a successful startup, `/readyz` returns 200, then returns 503 after each post-startup failure injection: a stopped database, and schema-revision drift (for example the test changes `alembic_version`). Startup against an unmigrated database is M3, not T11 |
| T12 | Web: the `PrivyProvider` config object has `createOnLogin: "off"`, and neither the production entry point nor the production build output contains the fixture token provider. This checks configuration only and is not Privy evidence |
| T13 | Build: `uv sync --frozen` and the Python test suite on 3.14. `npm ci` and `next build`. Record the resolved versions |
| T14 | Fuzz: a set of crafted tokens (wrong claim types, oversized claims, odd headers, truncated parts) never returns 5xx except the injected A13 state |
| B1 | Browser, mocked web auth: with the injected fixture provider, an API call through the UI returns the owner's records, and they match T1's rows |
| R1-R4 | Real-provider checks above, when the builder authorizes a Privy app |

## Failure matrix

Rows A1-A13 and A24-A28 reject without any database access. A1-A4 send no signed token, A5-A12 and A24-A28 use signed test tokens through the real verifier (class: fixture), and A13 injects application state. Rows A14-A23 and A29 need Postgres. A20 and A29 are accepted tokens that reach the `users` upsert. Every rejection happens before any owner-scoped read or write.

| ID | Input | Response | Notes |
|---|---|---|---|
| A1 | No `Authorization` header | 401 `auth_required` | `WWW-Authenticate: Bearer` |
| A2 | Wrong scheme (`Basic ...`) or empty token | 401 `auth_invalid` | |
| A3 | Malformed token (not three parts, bad base64) | 401 `auth_invalid` | No claim read from unverified content |
| A4 | Token over 4096 characters | 401 `auth_invalid` | Rejected before parsing |
| A5 | Valid structure, signed by a different key | 401 `auth_invalid` | |
| A6 | Header `alg` is `none`, `HS256` or `RS256` | 401 `auth_invalid` | Not in the allow-list |
| A7 | Valid signature, `exp` in the past (beyond 10 s leeway) | 401 `auth_expired` | Client refreshes once |
| A8 | Valid signature, wrong `aud` (another app) | 401 `auth_invalid` | |
| A9 | Valid signature, wrong `iss` | 401 `auth_invalid` | |
| A10 | Valid signature, `sub`, `exp`, `iat`, `iss` or `aud` missing, or `exp`/`iat` with a wrong type that PyJWT does not reject as expired (null, list, bool `iat`, far-future numeric string) | 401 `auth_invalid` | Never a 500. A bool `exp` or a past numeric-string `exp` gives `auth_expired`, because PyJWT checks `exp` first |
| A11 | Valid signature, `sub` empty, not a string or without `did:privy:` | 401 `auth_invalid` | A body-supplied owner is never a fallback |
| A12 | Expired token with a bad signature | 401 `auth_invalid` | Does not reveal expiry to an unsigned caller |
| A13 | Verifier cannot run: verifier or key list missing from application state before decode, or `InvalidKeyError` from decode | 503 `auth_unavailable` | No owner access. Reachable only by damaged app state, so the test injects it. Startup with no valid key never reaches serving. Malformed token input never maps here |
| A14 | Database down during principal lookup | 503 `service_unavailable` | No partial write |
| A15 | Owner A token, body carries `owner_id` of B, at top level or nested | 422 `validation_error` | Nothing changes. P03 replaces FastAPI's default 422 body with the error envelope |
| A16 | Owner A reads B's record by ID | 404 | Same body as a missing record |
| A17 | Owner A updates or deletes B's record | 404 | B's row unchanged (check in Postgres) |
| A18 | Owner A lists records | A's records only | B's absent. Counts match direct SQL |
| A19 | Owner A requests a stream, resume or cancel on B's job (when such routes exist) | 404 | Applies from the first ticket that adds them |
| A20 | Rotation: token signed by the previous key | Accepted while the previous key is configured. 401 after removal | Fixture version of R2 |
| A21 | First request from a new DID | Exactly one row is added, in `users` only | Once wallet, signer or mandate tables exist, their row counts stay unchanged. The Privy-side wallet check is R3 |
| A22 | Owner A inserts a child record, or updates one of A's records to set a parent ID, that belongs to B | 404, same body as a random parent ID | No row inserted or changed. Applies from the first ticket with a parent reference |
| A23 | Owners A and B submit the same natural, idempotency or canonical key | Both succeed as separate rows | No cross-owner 409. Applies from the first ticket with such a key |
| A24 | Valid signature, `iat` more than 10 s in the future | 401 `auth_invalid` | Documents the clock-skew assumption |
| A25 | Valid signature, `aud` is a list that contains the app ID | 401 `auth_invalid` | Requires a plain string |
| A26 | Otherwise-valid signed token with a valid `sid` and a top-level `linked_accounts` claim: non-empty value, empty string, empty array, empty object and `null` | 401 `auth_invalid` | Rejects by claim presence. Edge OS policy, not a Privy guarantee |
| A27 | Valid signature and every other claim, `sid` missing, empty, longer than 255 characters or not a string | 401 `auth_invalid` | The good-`sid` case is A29 |
| A28 | Same as A26 for a top-level `custom_metadata` claim, and for both claims together | 401 `auth_invalid` | Same policy and limits |
| A29 | Valid access-shaped token: every required claim, a valid `sid`, neither `linked_accounts` nor `custom_metadata` | Accepted. A principal is derived and the `users` row exists | Positive control for A26 to A28. Needs Postgres |

**Error body shape.** P03 uses `{"error": {"code": "<id>", "message": "<text>"}}` unless P02 supplies a frozen shape. The status and code choices above are this profile's. P02 confirms the body shape.

## Local and deployment responsibilities

| Concern | Owner | Notes |
|---|---|---|
| Startup config validation | API process | [Configuration](#configuration) |
| Migrations | Operator or release step runs `alembic upgrade head` before the API | API refuses to start on mismatch |
| Durable identity | `users` table | Created on first verified request |
| Isolation | Application code plus tests | Principal-derived `owner_id` on every query |
| Test-state cleanup | Test harness | Label and run-ID scoped |
| Key rotation | Operator | Procedure above |
| TLS | Hosting layer | Privy requires HTTPS for token transit. Production CORS origins must be `https://` |
| Secrets store | Hosting layer | Holds `EDGE_OS_DATABASE_URL` and the verification keys |
| Database backups and PostgreSQL upgrades | Hosting layer | No vendor selected |
| Persistent trading worker | A later ticket | The worker needs the same database and its own service credentials. It holds no user token. Its lifecycle is not decided here |

A hosting vendor, a deployment, a managed database or a purchase is not selected or authorized by this profile. Production deployment needs an explicit later decision and builder authority.

## Acceptance check mapping

| Issue #6 check | Where this profile answers it |
|---|---|
| Startup/configuration, durable identity, isolation, migration, test-state cleanup responsibilities | [Configuration](#configuration), [Ownership](#ownership), [Recipes](#recipes-all-unexecuted), [Isolated instance](#isolated-instance-proposed-unexecuted), [Local and deployment responsibilities](#local-and-deployment-responsibilities) |
| Confirm request-to-persisted-record boundary | [Test boundary](#test-boundary), T1, T2 |
| Missing/invalid/expired/wrong-app rejection, server-derived ownership, cross-owner denial, fixture-versus-real evidence | [Failure matrix](#failure-matrix), [Ownership](#ownership), [Evidence classes](#evidence-classes) |
| Verification-key, rotation and token-delivery mechanism | [Token delivery](#token-delivery), [Key retrieval and rotation](#key-retrieval-and-rotation) |
| Remaining choices, reasons, verification requirements. Proposed instructions are not proof | [Decision table](#decision-table), [Remaining bounded questions](#remaining-bounded-questions). Every command carries `UNEXECUTED` |

## Remaining bounded questions

None of these reopens a settled product decision.

| ID | Question | Owner | Blocks |
|---|---|---|---|
| Q1 | Does the builder authorize a Privy development app and its Dashboard verification key for R1-R3 and the manual browser run? | Builder | Any claim that Privy integration works |
| Q2 | Is the Dashboard key Ed25519 or EC P-256? The docs say both. SDK source imports it as ES256 (P-256). P03's startup check enforces P-256 and R1 confirms it | P03 with Q1 | D3, D4 |
| Q3 | Is the per-app JWKS endpoint seen in SDK source real and supported for a Python verifier, does the token carry a `kid`, and does the old key stay valid after rotation? The docs pages P01 read say nothing | P03 with Q1 | D4 refinement |
| Q4 | Does a Dashboard setting, besides the SDK flag, also create wallets at login? The reviewed page covers the SDK flag only | P03 with Q1 | D11, R3 |
| Q5 | Which Privy login methods does the product offer? A connected wallet is not an identity (Ownership rule 6) | Builder, P43 | P03 login UI |
| Q6 | Should PostgreSQL row-level security back the application owner filter? | Builder | Defense in depth, not P03 start |
| Q7 | Access-token lifetime, now 1 hour by default. A shorter value narrows the post-logout window | Builder | None |
| Q8 | `owner_id` shape, error body shape and any shared immutable record that needs a cross-owner unique key. Proposed: internal UUID `users.id`, the body above and owner-scoped uniqueness | P02 | P02 contracts |
| Q9 | Production install of `psycopg`: binary wheel or source build | Hosting decision | Deploy |
| Q10 | Hosting for API, web, database and the persistent worker | Builder | Deploy only |
| Q11 | TypeScript pin. The registry shows 7.0.2. P01 did not check it against Next 16.3.8. P03 pins the version that `next build` accepts and records it | P03 | P03 web build |

## Claims this profile cannot verify

- That PyJWT verifies a real Privy token. Only R1 shows this.
- That the Privy Python SDK lacks a verifier. A summarized fetch of the Python setup page found none. The page or the summary may omit it.
- That all pinned versions install and interoperate, including `httpx` on Python 3.14. Only P03's lock and tests show this. P01 read package metadata only.
- That Next.js 16.3.8 and `@privy-io/react-auth` 3.47.0 run together. P01 checked peer ranges, not behavior.
- That `postgres:18.6-trixie` accepts the volume path shown. P03 checks the image documentation.
- That real tokens carry `aud` as a plain string, a `sub` that starts `did:privy:` and fits 255 characters, and an `iat` consistent with the 10-second leeway. These come from doc examples and SDK source excerpts.
- That real access tokens never carry top-level `linked_accounts` or `custom_metadata`, and that real identity tokens carry at least one of them. The Tokens page says `sid` appears in both token types, so `sid` cannot separate them. The identity-data policy rests on the docs claim lists and SDK source excerpts. If a real identity token carries neither claim, this API accepts it as a same-user credential with a default lifetime of 10 hours. Only R1 and R4 test this.
- That Privy never reuses or merges a DID after a user is deleted.
- That `createOnLogin: "off"` is the only wallet-creation path.
- That the API host clock stays within 10 seconds of Privy's.
- That the SDK source excerpts match the current SDK. P01 read excerpts of two versions and did not fetch the package.
- Any wallet isolation. This profile creates no wallet and does not qualify wallet enforcement.

## Sources

Accessed 2026-10-06. Context7 library IDs are in parentheses.

- Privy, [Access tokens](https://docs.privy.io/authentication/user-authentication/access-tokens): claims, ES256, header and cookie delivery, SDK and library verification, Dashboard verification key. (`/llmstxt/privy_io_llms_txt`; full page also read through Exa fetch of the `.md` version.)
- Privy, [Tokens](https://docs.privy.io/authentication/user-authentication/tokens): lifetimes, backend verification, HTTPS, no tokens in URLs or logs, and the statement that `sid` appears in both access and identity tokens.
- Privy, [Optimize your setup](https://docs.privy.io/recipes/dashboard/optimizing): static `jwtVerificationKey`, manual update after rotation.
- Privy, [Automatic wallet creation](https://docs.privy.io/basics/react/advanced/automatic-wallet-creation): `createOnLogin` values, default `off`.
- Privy, [Python setup](https://docs.privy.io/basics/python/setup) and [llms.txt index](https://docs.privy.io/llms.txt): Python SDK pages. No token-verification method found.
- Privy, [Identity tokens](https://docs.privy.io/user-management/users/identity-tokens): identity-token claims (`linked_accounts`, `custom_metadata`), used for the identity-data policy.
- Privy Node SDK source, as search excerpts: [unpkg `@privy-io/node@0.28.0` `src/lib/auth.ts`](https://app.unpkg.com/@privy-io/node@0.28.0/files/src/lib/auth.ts) and [jsDelivr `@privy-io/node@0.34.0` `src/lib/auth.ts`](https://cdn.jsdelivr.net/npm/@privy-io/node@0.34.0/src/lib/auth.ts). Package-source evidence, not documentation.
- Issue [#6](https://github.com/edge-os-app/edge-os/issues/6): builder acceptance of the request-to-record test boundary.
- PyJWT (`/jpadilla/pyjwt`, 2.15.1): ES256 decode, `algorithms`, `require`, `leeway`, exception classes.
- FastAPI (`/websites/fastapi_tiangolo`): `HTTPBearer`, dependency overrides, lifespan, `TestClient`.
- SQLAlchemy 2.0 (`/websites/sqlalchemy_en_20`): `postgresql+psycopg://` URL, sessions.
- Alembic (`/websites/alembic_sqlalchemy`): `upgrade head`, `check`, head comparison.
- pydantic-settings (`/pydantic/pydantic-settings`): prefix, secrets, required-field errors.
- Next.js (`/vercel/next.js/v16.2.9`): `NEXT_PUBLIC_` inlining, Node `>=20.9.0`, CSS and Tailwind import.
- PyPI JSON, npm registry and Docker Hub tags API: versions, Python classifiers, image tags and digest.
- Exa note: the first `web_search_exa` call hit a free rate limit and returned nothing. A retry returned official Privy pages. None named a JWKS URL for access tokens. `web_fetch_exa` returned the full `.md` text of the access-tokens, tokens, identity-tokens, optimizing and automatic-wallet-creation pages. The Privy Python setup and `llms.txt` findings came from `WebFetch`, which summarizes the page with a small model. Treat those two as lower confidence.
- Controller input `p01-auth-reference-patterns@1` (SHA256 `b789f10ec79b0da7a999c4a70c0e3d39e52de41afc6ccebde978501a201fe3c2`): patterns and cases adapted here. No source file was copied. The inspected TX Odds/Veridex and OKX/Assensus files were not read by this ticket.
