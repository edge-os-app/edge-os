# Kuru Flow adapter qualification package

Task `OC-P20-ADAPTER-PREP-20261011-01`, v1, issue #19. The isolated offline adapter package is `apps/api/src/edge_os_api/kuru_flow/`. This package records its local qualification, the researched restriction gap and the exact future live-test packet.

Stage: **offline preparation only.** No provider request, wallet, funding, signature, broadcast, swap or policy change is run. Full P20 issue #19 stays OPEN.

## Proposed verdicts

- **OFFLINE ADAPTER: local preparation.** The adapter parses the supported quote schema, prepares a validated immutable unsigned transaction candidate from an explicit approved configuration, and normalizes supplied observations. Every mandatory value is compared with the exact decoded candidate bytes. All checks are `LOCAL_TESTED` over authored and documented fixtures.
- **LIVE qualification: NOT_RUN.** No route/network/deployed-ABI/transport, policy, wallet, funding, signature, broadcast or receipt evidence exists. Exact-byte policy matching on the opaque route and deployed bytecode identity stay unqualified.

## Documents

- [SOURCE_FIXTURE_MANIFEST.md](SOURCE_FIXTURE_MANIFEST.md) - the fixture labels, hashes, provenance and the source pins.
- [LIVE_TEST_PACKET.md](LIVE_TEST_PACKET.md) - the exact bounded future live-test proposal, with consequential values UNSET.
- [VERIFICATION_RECIPE.md](VERIFICATION_RECIPE.md) - the owned offline verification recipe and feature-map proposal.
- [../implementation/KURU_FLOW_ADAPTER_PROFILE.md](../../implementation/KURU_FLOW_ADAPTER_PROFILE.md) - the implementation-facing profile.

## Mandatory honest limits

1. The supported quote schema is the documented K2 shape. The K3 `buildResponse`/`path` shape stays unknown; its presence blocks.
2. The function selector is a supplied constant. Computing an Ethereum selector or transaction hash needs Keccak-256, which is not installed. SHA3-256 is never substituted.
3. The documented `transaction.to` label ("Router contract address") conflicts with the source-inspected `KuruFlowEntrypoint`. The adapter checks `to` against the approved entrypoint; which address is correct stays `UNKNOWN` until live/deployed qualification.
4. Deployed mainnet bytecode identity versus the pinned public source stays `UNKNOWN`.
5. The opaque route `program` bytes cannot be pinned by any documented provider-policy operator. That mandatory control stays `UNSUPPORTED` at the independent-policy layer.
6. No `RECORDED` provider response exists. All fixtures are `AUTHORED` stand-ins for documented response shapes. An invented payload is not a published example.

## Authority

The builder owns the consequential live configuration and the financial approval. This package selects no live value, network, provider or credential. It grants no spending, signing, funding, broadcast, deployment, publication or tracker authority.
