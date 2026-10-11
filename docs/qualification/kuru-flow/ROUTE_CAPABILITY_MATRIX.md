# Kuru Flow route capability matrix

Prepares Probe B's network, deployment, ABI, quote/build/transport and control-state picture. Source pins and check dates are in [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md). Prepared 2026-10-10.

## 1. Network and deployment separation

The design requires an explicit choice of Monad mainnet `143` or testnet `10143`. Approval for one never approves the other ([P15](../../contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md)).

| Item | Monad mainnet `143` | Monad testnet `10143` |
|---|---|---|
| Flow entrypoint contract | Documented: `KuruFlowEntrypoint` `0xb3e6778480b2E488385E8205eA05E20060B813cb` | **Not listed** |
| Flow router contract | Documented: `KuruFlowRouter` `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2` | **Not listed** |
| Flow forwarder | Documented: `KuruForwarder` `0x974E61BBa9C4704E8Bcc1923fdC3527B41323FAA` | Not listed as Flow |
| Quote/build API host | Documented: `https://ws.kuru.io` | Not documented for testnet |
| Order-book Router (factory) | Documented: `0xd651346d7c789536ebf06dc72aE3C8502cd695CC` | Documented: `0x7EFbE105Ca7415dE98F96622173458ac1c054630` |
| WMON | Documented: `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A` | Not listed |
| MON-USDC market | Documented: `0x065C9d28E428A0db40191a54d33d5b7c71a9C394` | Documented: `0xa241896A7Dbe8a550D2E5fF7A914bB1989ceD2D9` |

Consequences:

- **Flow is documented on mainnet `143` only.** The testnet section documents order-book contracts but no Flow entrypoint or router. The design's rule, "Prefer testnet only if the complete selected Flow path is verified", cannot be met from documentation. Testnet Flow stays **UNKNOWN**.
- Mainnet `143` is the only documented Flow path. It requires the builder's separate approval for the exact controlled amount and financial scope before any execution ([Exact Monad operation](../../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#exact-monad-operation)).
- The quote API example uses native MON as the input token and mainnet USDC `0x754704Bc059F8C67012fEd69BC8A327a5aafb603` as the output. This corroborates a mainnet orientation, but it does not prove the API rejects testnet calls.

## 2. Flow integration surface (documented / source-inspected)

Documented as capability. Not a deployed-ABI or live claim.

| Element | Documented / inspected detail | Status |
|---|---|---|
| Quote/build endpoint | `POST https://ws.kuru.io/api/quote` | documented |
| Quote authentication | Bearer JWT from `POST /api/generate-token`, or `X-API-Key` header | documented |
| Quote rate limit | JWT route: 1 request per second, burst 1 | documented |
| Quote request fields | `userAddress`, `tokenIn`, `tokenOut`, `amount`; exactly one of `slippageTolerance` (basis points, 1-10000) or `autoSlippage`; optional `referrerAddress`, `referrerFeeBps` (0-10000) | documented |
| Quote response fields | `type`, `status`, `output`, `path` (SwapRoute), `buildResponse` (BuildResponse), `gasPrices` | documented; `path`/`buildResponse` inner schema not published |
| On-chain entrypoint | `KuruFlowEntrypoint` with `executeSwap(SwapIntent, FeeCollection, program)` and `executeSwapWithReceiver(SwapIntent, FeeCollection, program, receiver)` | source-inspected, pinned commit |
| Router call | `IKuruFlowRouter.executeRoute(tokenIn, amountIn, tokenOut, minAmountOut, program)` | source-inspected, pinned commit |
| Flow intent struct | `SwapIntent { tokenUserBuys; minAmountUserBuys; tokenUserSells; amountUserSells; }` (bounded quote from the pinned file) | source-inspected, pinned commit |
| Fee struct | `FeeCollection { feeCollectorAddress; feeBps; referrerAddress; referrerFeeBps; isInTokenFee; }` | source-inspected, pinned commit |

The `program` bytes are the route. The public contract treats them as opaque and forwards them to the router. The published API does not document the `program` encoding.

## 3. Control-state matrix

Each mandatory control gets one classification:

- **documented**: an official page describes the behavior;
- **source-inspected**: the pinned public contract shows the behavior;
- **config-dependent**: the behavior depends on the selected Privy policy or app configuration and is not fixed by documentation;
- **requires live proof**: no documentary evidence establishes the enforced behavior.

| Mandatory control | Classification | Basis and limit |
|---|---|---|
| Fixed input amount | documented + source-inspected | `amountUserSells`; the quote takes an exact `amount`. |
| Minimum received output | documented + source-inspected | `minAmountUserBuys`; the entrypoint reverts `InsufficientAmountAfterFees` when the post-fee output is below it. |
| Maximum output / acquisition upper bound | **absent** | The intent has no maximum-output field. A fixed token-quantity sell ceiling therefore needs a separate acquisition bound ([EXIT-CAP-Q01](../../EDGE_OS_RESEARCH_CONTRACTS.md#exit-cap-q01-permission-model-qualification)). |
| Recipient | source-inspected | `executeSwap` sends to `msg.sender`; `executeSwapWithReceiver` sends to `receiver`. |
| Native MON versus ERC-20 notional | documented + source-inspected | `tokenUserSells == address(0)` means native; `msg.value` must cover `amountUserSells`. Native value is not the ERC-20 notional. |
| Token approvals | source-inspected | For an ERC-20 input the entrypoint approves the router for `amountIn`, then resets the approval to `0`. **Requires live proof** that no lasting allowance remains. |
| Route bytes / batches | source-inspected (opaque) | `program` is forwarded unchanged. Content and batch safety are **not** documented. |
| Fees | documented + source-inspected | `feeBps + referrerFeeBps <= 10000`; `isInTokenFee` selects input or output collection. Fee recipient and payout mechanics need live proof. |
| Gas | documented | Quote returns `gasPrices`. Exact gas budget is `UNSET`. |
| Residual holdings | **requires live proof** | Unknown program routes can leave partial or residual assets. Documentation provides no guarantee. |
| Outer contract / method allowlist | config-dependent | A Privy policy can restrict `to`, `chain_id`, `value` and decoded calldata by ABI ([Privy Ethereum examples](https://docs.privy.io/controls/policies/example-policies/ethereum)). |
| Opaque route enforcement | **requires live proof** | Documentation shows ABI-argument matching (for example `transfer.amount`). It does **not** show equality or bound checks on the opaque `program` bytes. An outer entrypoint allowlist does not prove route, amount or inventory enforcement. |
| Position-inventory enforcement | **requires live proof** | Privy policies do not read the Edge OS position ledger. Application attribution is not provider verification ([P15](../../contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md)). |
| Policy administration separation | config-dependent + requires live proof | Separate policy-administration credentials from the executor, then prove the executor cannot weaken policy. |
| Sign-only versus broadcast transport | documented | `POST /v1/wallets/{wallet_id}/rpc` with `eth_signTransaction` returns broadcast-capable `signed_transaction` RLP. Treat it as broadcast-capable and never broadcast it in preparation. |

## 4. Enforcement boundary

- The minimum-output guard is enforced **after fees** inside the entrypoint. It protects the received amount. It is not an upper bound on acquired inventory.
- The entrypoint sends the router `minAmountOut = 0`. The router's own minimum-output protection is therefore absent at this layer; the entrypoint's post-fee check is the only documented guard.
- An outer `to == KuruFlowEntrypoint` allowlist is necessary but insufficient. It does not constrain the opaque `program`, the token notional or the fee fields beyond what a decoded-ABI rule can express.
- If a mandatory restriction is unenforceable at the selected layer, the affected action stays unsupported. A new approver or contract wrapper is a material architecture choice for the builder.

## 5. Open unknowns (exact missing inputs)

- Whether the selected Privy policy can enforce any bound on the opaque `program` bytes. `UNKNOWN`.
- The deployed mainnet entrypoint/router bytecode identity versus the pinned public source. `UNKNOWN`.
- Whether the quote API restricts calls to mainnet `143`. `UNKNOWN`.
- The `buildResponse` schema and whether it returns a ready-to-send transaction, calldata, or a `program` only. `UNKNOWN`.
- Flow support on testnet `10143`. Not documented.
