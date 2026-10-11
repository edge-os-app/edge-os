# Source and fixture manifest

Prepared 2026-10-11 at base `9210bc1d054f1d5623693f787737a7b80563185a`. This manifest lists the fixtures and the sources behind the offline adapter. Every fixture is labelled `AUTHORED` or `DOCUMENTATION`. No `RECORDED` response exists.

## Fixture file

- Path: `apps/api/tests/kuru_flow/fixtures.json`
- Schema tag: `p20-kuru-flow-adapter/1`
- File SHA256: `c61c6cb137fd8e8b4e907ba84e17a40a837c777f699146e4b33f104b5986ec86`
- Each fixture hash is the SHA-256 of the canonical JSON (`sort_keys`, compact separators) of its `response` object. The test `test_fixture_manifest_is_intact` recomputes every hash.

| Fixture | Label | Purpose | SHA256 |
|---|---|---|---|
| `authored-execute-swap` | AUTHORED | Native MON input, `executeSwap` layout | `ed82d73a26eb0065db79855067da792b69786886ec95856302e656e3cc27562d` |
| `authored-execute-swap-with-receiver` | AUTHORED | Explicit receiver, `executeSwapWithReceiver` layout | `dfb9c2b6a711c8ceeb55ffff20b159f50da45446b6dc480f2e4dd84bfd775002` |
| `authored-erc20-execute-swap` | AUTHORED | ERC-20 input, `value` 0 | `1dd84e50710421daf7cec8865c34409144aefb9309227155fe8f84f2ec1cc15d` |
| `authored-missing-calldata` | AUTHORED | `transaction` object without `calldata` | `8ea82b92de5aefc4a48d273b90ca817756eabd30fa06ed65d30ef8ed9084bdea` |
| `documentation-build-response` | DOCUMENTATION | K3 `path`/`buildResponse` shape | `35f5d120dceb8e8d418b77fd2d6ac798bb22361182ba1cb5c855f360ef6e33f2` |
| `documentation-transaction-calldata` | DOCUMENTATION | K2 shape with unprefixed `calldata` | `ed82d73a26eb0065db79855067da792b69786886ec95856302e656e3cc27562d` |

The two `executeSwap` calldata values are identical because both use the same authored intent; the documentation fixture differs only in that its `calldata` is stored without the `0x` prefix, as the K2 guide documents.

## Source pins

| ID | Source | Supports | Class |
|---|---|---|---|
| K1 | `https://docs.kuru.io/contracts/Contract-addresses` | Mainnet `143` Flow addresses; testnet `10143` list without Flow | `DOCUMENTED` |
| K2 | `https://docs.monad.xyz/guides/kuru-flow` (rechecked 2026-10-11) | `POST /api/quote`; response `output`, `minOut`, `transaction { to, calldata, value }`, `gasPrices`; `calldata` has no `0x` prefix; native MON `0x0`; ERC-20 allowance check | `DOCUMENTED` |
| K3 | `https://docs.kuru.io/kuru-flow/openapi.json` and `https://docs.kuru.io/kuru-flow/flow-overview` | `path`/`buildResponse` shape; server `https://ws.kuru.io` | `DOCUMENTED` |
| S1 | `Kuru-contracts-flow-public` at commit `70bc0c93c073f78697b99848eedefbf5dbe698c7`, `src/entrypoint/KuruFlowEntrypoint.sol`, SHA256 `15e19667ee20389b396a51143dccf7bbd31a701c610f1d78978c84f3b7fd1841` | `executeSwap`/`executeSwapWithReceiver`; router call; fee rules; min-output-after-fees; `minAmountOut = 0`; approval reset | `SOURCE_INSPECTED` |
| S2 | same repo, `src/entrypoint/KuruFlowEntrypointTypes.sol`, SHA256 `44d913012de00a2814e62f1e9c45c4408c8407c0457325de41efabecd05df1ac` | `SwapIntent { tokenUserBuys; minAmountUserBuys; tokenUserSells; amountUserSells; }`; `FeeCollection { feeCollectorAddress; feeBps; referrerAddress; referrerFeeBps; isInTokenFee; }` | `SOURCE_INSPECTED` |
| P1 | `https://docs.privy.io/controls/policies/overview` and `.../example-policies/ethereum` (checked 2026-10-11) | Policy condition sources, fields and operators | `DOCUMENTED` |
| P2 | `https://docs.privy.io/api-reference/wallets/ethereum/eth-sign-transaction` | `eth_signTransaction` returns broadcast-capable bytes | `DOCUMENTED` |

The pinned `Kuru-contracts-flow-public` source carries `SPDX-License-Identifier: BUSL-1.1`. No source code is copied into this package. Only field names and two minimal struct shapes are referenced with attribution. The source license does not authorize copying a full contract implementation.

## Recorded-source limit

No provider response was captured. The header of `fixtures.json` records `recorded_responses: NONE`. A `RECORDED` response requires `_provenance {source_url, captured_at, sha256}` metadata and is rejected without it. A missing capture does not prove the provider's live schema.
