---
status: accepted
---

# Use a Python API, PostgreSQL, Next.js and Privy authentication

Builder decision, 2026-10-06: use Python/FastAPI for the application backend, PostgreSQL for durable application records, Next.js for the frontend and Privy for user authentication. The [specification](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-application-stack) owns the detailed boundary. This records the selected direction, not a working integration or a completed P01.

Python keeps the research/compiler/simulator implementation close to the inspected Python references. A separate Next.js frontend can implement the approved design without owning quantitative or financial truth. Compared with an all-TypeScript backend, this adds an API boundary and two toolchains; compared with a file or in-memory store, PostgreSQL requires setup and migrations but supplies a durable transactional store for the accepted multi-user and worker records. These are engineering reasons for the selected shape, not measured performance claims or evidence that reference code is safe to reuse.

FastAPI derives the application principal from verified Privy claims and applies owner-scoped access to PostgreSQL records. Frontend identity, a token's presence or a supplied owner ID is insufficient. Login grants no agent-wallet creation, funding, signing or trading permission. The restricted execution service and mandate remain separate under [ADR 0005](0005-model-and-execution-authority-boundary.md).

Preserve the approved design's tokens and styles. The builder permits CSS or Tailwind; choose the smaller compatible translation once the actual export exists, rather than rewrite working styles to enforce a preference. Versions, database access/migration tooling, authentication key/session handling, configuration, hosting and persistent-worker lifecycle still need scoped decisions and executed checks. No dependency installation, cloud purchase, wallet operation, deployment or publication is authorized by this record.
