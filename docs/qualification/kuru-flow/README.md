# Kuru Flow preparation package

Event OC-P20-PREP-20261010-01. Worker pane `%7`, branch `ticket/p20-route-preparation`, base `47ed61049683dfd86f6fad44130955d81f8628c7`. Prepared 2026-10-10.

Stage: **documentation and preparation only.** This package does not implement an adapter, run a provider request, create or fund a wallet, sign, broadcast or spend. Full P20 issue #19 stays OPEN.

## Purpose

Give the controller and the builder a source-backed preparation package for Probe B through the actual Edge OS application. The package records the documented route, the control requirements and the exact missing qualification inputs. It separates the documentation verdict from the unrun live qualification.

## Proposed verdicts

- **DOCUMENTATION / PREPARATION coverage: PASS within the scope below.** The package separates mainnet and testnet, identifies the documented Flow deployment and ABI from authoritative sources, maps the control requirements, lists the exact missing inputs and preserves the acceptance sequence.
- **LIVE qualification: UNRUN.** No route/network/ABI/transport, policy, wallet, funding, signature, broadcast or receipt evidence exists.

A documented source shows the provider's description. It does not prove a working Edge OS integration. Every material limitation stays visible in the documents below.

## Headline source-backed findings

1. The Kuru contract-address page documents `KuruFlowEntrypoint` and `KuruFlowRouter` on **Monad mainnet 143 only**. The testnet 10143 section lists the order-book Router, Margin Account, Forwarder, Deployer and Utils, but **no Flow contract**. Testnet Flow support therefore stays **UNKNOWN / unsupported by documentation**.
2. The Flow integration surface is a hosted quote/build API plus an on-chain entrypoint contract. The entrypoint supplies a fixed input and a minimum received amount, and it does not expose a maximum-output bound.
3. The entrypoint passes `minAmountOut = 0` to the router and validates the post-fee minimum itself. This is a source-inspected behavior of the pinned public contract. It does not prove deployed-ABI equivalence or live behavior.
4. The user's outer contract allowlist does not prove control of the opaque route `program` bytes, the token notional or the inventory. This remains unenforced by documentation and needs live proof or a different enforcement design.

## Documents

- [ROUTE_CAPABILITY_MATRIX.md](ROUTE_CAPABILITY_MATRIX.md) - networks, deployment, ABI, quote/build/transport, and the per-control enforcement state.
- [INTEGRATED_PROBE_B_PLAN.md](INTEGRATED_PROBE_B_PLAN.md) - the staged sequence, recovery and durable references, P16 reuse map, and the preserved acceptance sequence.
- [CONFIGURATION_FIELDS.md](CONFIGURATION_FIELDS.md) - the complete live-packet field checklist. Unknown fields are `UNSET`/`UNQUALIFIED`.
- [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md) - exact source pins, URLs, dates and content hashes, including the Context7 fallback.

## Scope and exclusions

Owned new path: `docs/qualification/kuru-flow/` only. No application code, shared documents or specifications, scripts, migrations, lockfiles, or new helper or probe program. No credential or environment-file discovery, account login or dashboard, RPC or provider call, quote or build request, SDK execution against a provider, wallet setup, signature, funding, swap or paid collection.

## Authority limits

The builder owns the consequential live configuration and the financial approval. This package selects no numeric production value, no network for live use and no provider. It grants no spending, signing, funding, broadcast, deployment, publication or tracker authority.
