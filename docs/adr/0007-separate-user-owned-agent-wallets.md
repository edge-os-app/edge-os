---
status: accepted
---

# Give each trading agent a separately funded user-owned wallet

Builder decision, 2026-10-05: assign each trading agent its own user-owned wallet and require explicit funding and wallet-bound permission. Agent A cannot spend Agent B's funds or sell its holdings. This supersedes the shared-wallet portion of [ADR 0003](0003-durable-shared-wallet-accounting.md); its durable accounting and renewal rules remain in force within each agent wallet. The [specification](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-wallet-ownership-and-funding) owns the required lifecycle and user controls.

Separate wallets make funding, holdings and action ownership easier to inspect and reduce cross-agent inventory-allocation ambiguity. The rejected shared-wallet alternative needed cross-agent reservations and attribution of identical tokens. Separate wallets instead require per-wallet funding, gas management and permission binding. Several positions within one agent wallet still require atomic reservations and inventory attribution. A combined account view grants no cross-wallet authority.

This accepts product architecture, not a qualified signer mechanism. Privy documents multiple user wallets, but separate addresses, including HD wallets derived from a shared seed, do not establish independent key-compromise boundaries or prevent an overbroad backend credential from reaching another wallet. Qualification must prove wallet-specific access, owner recovery/removal and cross-agent denial. No wallet creation, delegation, funding, spending, production implementation or publishing is authorized by this ADR.
