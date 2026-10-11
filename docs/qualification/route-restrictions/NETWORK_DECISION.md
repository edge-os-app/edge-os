# Network eligibility and route-based decision

Deliverable 1. Prepared 2026-10-10. Source pins are in [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md).

## Question separated into two parts

1. **Event eligibility.** May the hackathon submission use mainnet or testnet?
2. **Provider availability.** On which network can the exact selected Kuru Flow route actually be established?

These are different questions. A permitted network is not a supported provider network.

## Event eligibility

- The saved brief `docs/research/00_HACKATHON_BRIEF.md` records that mainnet or testnet deployment is allowed.
- The current public pages (K6) describe the deliverables: a working product, a demo, a short write-up and a code link. The public pages state no network mandate.
- The authenticated application-platform rules remain the authoritative source. They are not publicly inspectable without login.
- Result: **event eligibility permits either network.** No public source found requires mainnet. Do not assume a mainnet mandate.

## Provider availability

- Mainnet `143`: documented Flow entrypoint and router (K1). Bounded `eth_getCode` shows deployed code at both addresses (SOURCE_EVIDENCE section 4, #3/#4). The quote host is documented as `https://ws.kuru.io` (K3).
- Testnet `10143`: the official testnet table lists the order-book Router, Margin Account, Forwarder, Deployer and Utils, with **no Flow entrypoint or router** (K1). Bounded `eth_getCode` shows deployed code at the order-book Router (#5). The mainnet Flow entrypoint address is empty on testnet (#6).
- Result: **Flow is documented on mainnet `143` only.** Testnet Flow stays `UNKNOWN`, not proved unsupported. The table omission and the empty mainnet address on testnet do not prove no Flow testnet deployment exists elsewhere.
- The quote API documents no chain selector (K3). Whether the API rejects testnet calls is `UNKNOWN`. The documented quote example uses mainnet-oriented native MON input.

## Decision

- **Prefer testnet only if the complete selected Flow path is verified.** It is not verified. Testnet Flow support is `UNKNOWN`.
- **Mainnet `143` is the only documented Flow path.** A mainnet live test needs the builder's separate approval for the exact controlled amount and financial scope before any execution.
- **The route decision is the builder's.** The package proposes: keep testnet as the first choice, and treat mainnet as the fallback only when the builder approves the exact bounded packet and the network is the reason for the change.
- **No silent switch.** A network change is a recorded decision, not an automatic fallback.

## Separately recorded facts

- The builder stated he will deposit mainnet MON when the authorized test is ready. This records willingness. It is not approval for a swap, a policy change, or a mandate. A deposit does not approve swaps.
- Testnet MON is not the Flow quote asset or liquidity. Holding testnet MON does not prove a testnet Flow route.
- A different order-book route is an explicit architecture and scope decision. It is not a silent fallback.

## What is required to resolve testnet

Lead: the Kuru SDK quickstart labels router `0x1f5A250c4A506DA4cE584173c6ed1890B1bf7187` and margin account `0xdDDaBd30785bA8b45e434a1f134BDf304d6125d9` as testnet. These addresses conflict with the deployment table. Do not treat them as a testnet Flow proof. See [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md) section 2.

1. A source-backed testnet Flow entrypoint/router address, or an official statement that Flow is mainnet-only.
2. A quote/build response for a testnet request that freezes the actual schema (`transaction.calldata` per K2, `buildResponse` per K3, or another shape).
3. Deployed bytecode identity for the entrypoint and router against the pinned source.

Until 1–3 exist, the selected route is `UNQUALIFIED` on testnet.
