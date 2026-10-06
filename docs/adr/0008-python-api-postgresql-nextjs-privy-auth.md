---
status: accepted
---

# Use a Python API, PostgreSQL, Next.js and Privy authentication

Builder decision, 2026-10-06: use Python/FastAPI for the application backend, PostgreSQL for durable application records, Next.js for the frontend and Privy for user authentication. The [specification](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-application-stack) owns the detailed boundary. This records the selected direction, not a working integration or a completed P01.

Python keeps the research/compiler/simulator implementation close to the inspected Python references. A separate Next.js frontend can implement the approved design without owning quantitative or financial truth. Compared with an all-TypeScript backend, this adds an API boundary and two toolchains; compared with a file or in-memory store, PostgreSQL requires setup and migrations but supplies a durable transactional store for the accepted multi-user and worker records. These are engineering reasons for the selected shape, not measured performance claims or evidence that reference code is safe to reuse.

FastAPI derives the application principal from verified Privy claims and applies owner-scoped access to PostgreSQL records. Frontend identity, a token's presence or a supplied owner ID is insufficient. Login grants no agent-wallet creation, funding, signing or trading permission. The restricted execution service and mandate remain separate under [ADR 0005](0005-model-and-execution-authority-boundary.md).

Preserve the approved design's tokens and styles. The builder permits CSS or Tailwind; choose the smaller compatible translation once the actual export exists, rather than rewrite working styles to enforce a preference.

## P01 proposed decisions, 2026-10-06

The [P01 profile](../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md) owns the detail, versions, reasons and verification requirements. It is a proposed profile. P03 implements it and runs its checks. Nothing in it has run. P01 proposes these choices inside this ADR. They take effect only when the builder accepts this change:

- The browser sends the Privy access token as an `Authorization: Bearer` header directly to FastAPI. No cookie session and no development-auth bypass.
- FastAPI verifies the token with PyJWT: `ES256` only, required `exp`, `iat`, `iss`, `aud` and `sub`, issuer `privy.io`, audience equal to the configured Privy app ID.
- The verification key is a static public key from configuration, with an optional previous key for rotation. The Privy documentation pages reviewed name no JWKS endpoint for access tokens. SDK source suggests one exists. The profile does not adopt it.
- The API holds no Privy app secret. Login creates a user row and no wallet, signer or trading permission.
- Storage is PostgreSQL 18 through SQLAlchemy 2.0 and psycopg 3. Alembic applies migrations in a separate step before the API starts.

Hosting, the persistent-worker lifecycle, a real-provider authentication check and the remaining questions in the profile need later decisions. No dependency installation, cloud purchase, Privy app creation, wallet operation, deployment or publication is authorized by this record.
