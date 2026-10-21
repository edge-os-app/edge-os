# F6: dependency advisory and reachability assessment (read-only)

Date: 2026-10-12. Scope: `apps/web` production dependencies at the lockfile on base `6fab6f2`. No lockfile, package or dependency was changed. `npm audit fix` was not run.

## Findings

- `npm audit --omit=dev` and `npm audit` both report **25 advisories: 24 moderate, 1 high**.
- **All 25 are transitive through `@privy-io/react-auth@3.47.0`.** npm's suggested fix is a downgrade to `@privy-io/react-auth@3.6.1`, a semver-major change in the wrong direction. It was not taken.
- **High (`ws`):** the affected range is `8.0.0 – 8.20.1`. Installed `ws` copies include 1.0.6, 1.0.7, 7.5.13, 8.18.0 (×5), 8.18.3 (×3), 8.21.0, 8.21.3 and 8.22.0, so some copies are in range.
- **Other flagged packages:** `uuid@8.3.2` (×2) and `uuid@9.0.1` (×8), and `decode-uri-component@0.2.2`.

## Reachability evidence

A scratch production build (`next build` into `.next-audit`, deleted after the check) gave these results:

- The text `privy` appears in one server-side rendering chunk (`server/chunks/ssr/…`). Minified client chunks were not attributed by package name.
- No `ws` server code appears in the server or static output. The search used the server-only markers `perMessageDeflate` and `Sec-WebSocket-Key`. The application runs no WebSocket server; `ws` is a client-side wallet SDK dependency.
- `decode-uri-component` does not appear in the static chunks.

## Assessment

- The application does not run the `ws` server path that the high advisory describes, so the high advisory is not reachable in the built output. This is a build inspection, not a proof for every runtime path inside the wallet SDK.
- The moderate advisories sit inside the third-party wallet SDK. The application does not call those packages directly.
- **Residual risk:** a later Privy release could make them reachable, and the SDK runs in the owner's browser with wallet authority.

## Disposition needed (controller)

No lockfile change is made in this milestone. Options for a controller repair disposition:

1. Upgrade `@privy-io/react-auth` to a release whose tree has fixed `ws`/`uuid`, after a sign-in regression run.
2. Add npm `overrides` for `ws` (≥ 8.21.0) and `uuid`, with an SDK regression run.
3. Accept the residual risk for the local milestone and re-check before public exposure.

## Correction: wallet-dependency advisory reachability (2026-10-21)

Date: 2026-10-21. Base `d1f3867ba490e060505b7cfc176071c78fe223e0`, tree `40627e1ca58afbe19f895c4daaa2aee090ebe55e`. This section corrects the reachability reasoning in the F6 section above. It keeps F6 as history and does not rewrite its counts or its build.

### Named advisories

- GHSA-96hv-2xvq-fx4p (ws, high): peer fragments exhaust receiver memory. Fixed ws8 8.21.0, ws7 7.5.11.
- GHSA-58qx-3vcg-4xpx (ws, moderate): TypedArray close-reason misuse. Fixed ws8 8.20.1.
- GHSA-vcc3-ghjq-m6fr (decode-uri-component, moderate): CPU use on malformed input. `0.2.2` affected, `0.5.0` patched.
- GHSA-w5hq-g745-h8pq (uuid, moderate): missing buffer bounds check in v3/v5/v6 when a buffer is supplied. Fixed 14.0.0. There is no patched 8.x or 9.x release.

### Dependency tree (R2, offline)

All four advisories are transitive through `@privy-io/react-auth@3.47.0`. The tree confirms these rows:

- `@reown/appkit@1.8.9` and its `appkit-controllers` / `appkit-utils` branches each reach `@walletconnect/utils > viem@2.36.0 > ws@8.18.3`.
- `@wagmi/connectors@6.2.0 > @walletconnect/utils > viem@2.23.2 > ws@8.18.0`.
- `viem@2.56.5 > isows@1.0.7 > ws@7.5.13`, and `viem@2.56.5 > ws@8.21.0`.
- `@walletconnect/jsonrpc-ws-connection@1.0.16 > ws@7.5.13`.
- `@walletconnect/utils@2.21.1 > query-string@7.1.3 > decode-uri-component@0.2.2`.
- `@metamask/*` branches reach `uuid@8.3.2` and `uuid@9.0.1`.

Fixed copies also present: `ws@7.5.13`, `ws@8.21.0`, `ws@8.21.3`, `ws@8.22.0`.

### Emitted build evidence (R5, R6, R7)

- Typecheck passed. The full current web test suite passed: 27 files, 329 tests.
- Build: Next.js 16.3.8 with Turbopack; routes `/`, `/_not-found`, `/app` are static.
- Exact build markers: the `ws` browser stub `ws does not work in the browser` appears in one client chunk, `static/chunks/2yf6ovaq6jl1z.js`. The Node `ws` implementation markers (`permessage-deflate`, `Sec-WebSocket-Key`, `WebSocketServer`) appear in zero client and zero server files.
- Six server `.nft.json` traces contain no path for `ws`, `uuid`, `decode-uri-component`, `query-string` or `isows`. The single `query-string` substring hit is Next's own `next/dist/server/app-render/get-asset-query-string.js`.
- No `uuid.v3(`, `uuid.v5(` or `uuid.v6(` call appears in the client or server output.
- The installed `next experimental-analyze` hard-codes the `.next` output directory and reports only route names, so it supplied no import-to-chunk map. Marker absence is supporting evidence only.
- The local fixture browser run (R7) served the build and loaded the landing with no `/v1` call and no Privy script; the 401 fixture path rendered "Sign in to start" and "Signing in does not create a wallet" at desktop and 390 px. The R7 build contains two `createOnLogin: "off"` literals.

### Residual risk: OPEN

No item below is closed. Missing markers cannot prove absence. A later SDK or build change could emit different code.

| Package or path | Status | Evidence type | Why it stays open |
|---|---|---|---|
| `ws` Node implementation (GHSA-96hv-2xvq-fx4p, GHSA-58qx-3vcg-4xpx) | OPEN | Positive stub-chunk identification; zero Node markers; zero NFT paths | The affected copies stay installed. Only the browser stub is emitted today; no import-to-chunk map proves exclusion for every path. |
| `decode-uri-component` (GHSA-vcc3-ghjq-m6fr) | OPEN | Zero markers; zero NFT paths; tree shows `query-string > decode-uri-component` | `query-string` is declared by `@walletconnect/utils` but no shipped module imports it. No emitted identity or chunk map. |
| `query-string` | OPEN | Zero markers; no NFT path | Declared dependency; no emitted identity. |
| `uuid` v3/v5/v6 buffer path (GHSA-w5hq-g745-h8pq) | OPEN | Zero v3/v5/v6 markers; zero `uuid` NFT paths; observed v4 use only | No import-to-chunk map. A fix needs a cross-major override (8/9 to 14), which this ticket does not permit. |
| `isows` | OPEN | Package export map shows the browser native path and the Node `ws` path; no emitted identity | No import-to-chunk map. |

The earlier F6 statement that the high advisory is server-only is superseded for the peer-fragment advisory. The relevant boundary is the browser/Node split: the browser uses the native WebSocket, and the emitted client carries only the `ws` browser stub.

### Disposition

No lockfile, dependency or source change. The named advisories remain OPEN residual risks before public exposure. Re-check the tree, the emitted build and the browser path when the wallet SDK changes. Real Privy login, real wallet creation and public hosting remain outside this assessment.
