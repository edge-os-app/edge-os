# Edge OS

Settled domain vocabulary for Edge OS research and strategy decisions.

## Language

**Loose intuition**:
A user-supplied market observation that needs clarification before it forms a testable hypothesis.
_Avoid_: Low-confidence strategy

**Executed quote volume**:
The amount of the declared quote asset represented by qualified trades during a declared interval.
_Avoid_: Net capital inflow

**Evidence status**:
The recorded finding about what retained observations and tests support for a declared claim.
_Avoid_: Confidence tier

**Live trial**:
An optional live-trading configuration with a declared learning objective and stopping point. It uses real capital.
_Avoid_: Paper trial, graduation stage

**Execution permission**:
Active user-approved authority for specified financial actions under a wallet-bound mandate.
_Avoid_: Evidence approval

**Position**:
An individually tracked exposure for a supported strategy and market in its agent's wallet, recorded alongside that wallet's aggregate exposure.
_Avoid_: Deployment, wallet balance

**Trading agent**:
A user-configured operator of an approved strategy, assigned its own agent wallet. Research assistance alone is not a trading agent deployment.
_Avoid_: Wallet owner, unrestricted signer

**Agent wallet**:
A user-owned wallet assigned to one trading agent, with separately funded balances and wallet-bound execution permission.
_Avoid_: Shared agent balance, AI credits

**Account overview**:
A combined view of the user's agents, wallets and positions. It is not a pooled balance or shared permission to spend.
_Avoid_: Shared trading wallet

**Funding**:
A confirmed capital transfer into an agent wallet, distinct from trading profit and execution permission.
_Avoid_: Activation, allowance renewal

**Strategy revision**:
An immutable version of a strategy's meaning, distinct from its drafts and deployments. Strategy evidence and execution permission refer to the exact revision they concern.
_Avoid_: Latest strategy

**Attributable inventory**:
The inventory assigned to a position from confirmed approved acquisitions and additions, adjusted for exits and other qualified balance changes. Unrelated transfers and inventory assigned to other positions are excluded.
_Avoid_: Wallet balance, sell permission
