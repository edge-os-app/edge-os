# H8 provider spend caps: sponsored (HOSTED_RECORD_V2_RUNBOOK §6)

Status: **documented**. No card-backed spend cap is configured. The sponsor's allocation is the cap.

## Provider accounts

| Provider | Use in this deployment | Funding | Cap | Remaining balance visible in |
|---|---|---|---|---|
| Nansen | research data | sponsored | the sponsor's allocation | the Nansen account dashboard |
| QuickNode | Monad RPC access | sponsored | the sponsor's allocation | the QuickNode account dashboard |
| Envio HyperSync | history source | free | the free allowance | the Envio account dashboard |

The exact sponsor names and allocation amounts are held in each provider account. This file does not copy an amount it
cannot verify from the provider dashboard. A reader who needs the amount reads it from that dashboard.

## Application-side caps

These still apply and do not replace the provider caps:

- `EDGE_OS_RESEARCH_BUDGET_*` bounds research spending.
- `EDGE_OS_USAGE_GLOBAL_*` bounds global usage.
- The shared USD 2.00 paid model and data ceiling remains the outer limit for paid provider calls.

## Limit

An account balance is not a hard stop by itself. A future card-backed provider cap needs the builder and a separate
recorded decision. This file records the sponsored state, not a new limit.
