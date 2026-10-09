# P13 spot replay runtime profile

P13 implements the adopted `p12.spot-replay/1` and `p12.essential-evidence/1` profile over an authored synthetic fixture. The public pure replay module preserves each P06 value and reason, validates both explicit essential bindings, and separately checks every primitive observation used by each full entry and exit expression. A decisive Boolean sibling does not hide future or unknown-delivery timing. Missing or operation-unused P06 reasons alone do not become a blanket action block; the adopted WC-06 and WC-14 distinctions remain in the regression suite.

The authenticated API creates an immutable owner-bound replay snapshot and returns that same snapshot for an identical idempotency key and input fingerprint. It stores the exact strategy revision, run configuration, fixture and dataset identity, window, balances, essential bindings, costs, calculation results and SHA-256 content identity. Retrieval checks ownership and content integrity and returns the stored result; it does not re-evaluate the strategy. The replay API uses the existing application auth and persistence wiring. It adds no provider, wallet, transaction or execution-permission path.

The web panel shows the new-run settings separately from the exact saved settings returned by retrieval, including the saved profile, revision/configuration/fixture, interval, starting balances, size, warm-up, costs and entry/exit bindings. A definitive HTTP 422 validation response releases that rejected body so corrected inputs can be submitted with a new key. Other uncertain outcomes retain the original body and key; editing visible fields does not change a retry. Reopening a saved result performs retrieval only.

The calculation remains a single-position synthetic replay. It settles a prior order, values the current sample, then evaluates signals. A next scheduled close is only an assumed fill proxy when explicitly qualified and available. The simulator uses saved fee and slippage fractions; unavailable next fills release reservations once. It reports quote-denominated balances, fee-inclusive basis, event history, metric states/reasons, and open-position marks. Gas, separate spread, routing, impact beyond the saved slippage proxy, capacity, real market-history qualification and executable fills remain outside scope. Synthetic results are not profitability claims or permission to trade.

## Verification boundary

Pure tests cover the adopted WC-01 through WC-14 cases and P12 distinction cases. API, web and mapped P03 checks cover owner separation, immutable/idempotent create and retrieval, saved settings display, correction after a definitive rejection, same-key retry after uncertainty, database integrity, restart retrieval and no replay POST on reopen. These checks establish local synthetic implementation behavior only; they do not establish external data or execution quality.

From the repository root, the relevant local commands are:

```sh
(cd apps/api && .venv/bin/pytest -q)
(cd apps/web && npm test -- --run && npm run typecheck && npm run build)
```

The assigned implementation report records the exact candidate and any mapped P03 command/evidence. A passing local test suite is not real-data qualification, fill qualification, cost qualification, financial approval or deployment authority.
