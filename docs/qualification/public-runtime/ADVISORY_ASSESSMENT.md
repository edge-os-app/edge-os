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
