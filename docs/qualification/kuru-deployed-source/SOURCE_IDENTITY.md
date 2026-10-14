# Source identity: Kuru Flow entrypoint and current router

Task `P21-DEPLOYED-SOURCE-L3-20261014-LOCAL-v1`. Base `98d89c5f41d48ce5f76051606e5fba0b767a9f3d`. Sources checked 2026-10-14 between 16:50 and 16:58 UTC.

## 1. Frozen inputs

The builder-approved read-only check of 2026-10-14 read Monad mainnet (chain `143`) at finalized block `0x6c1db44`, hash `0xa70294d7da3443ecb28da3aba4842edb19ba1d143eee2af2c1621cd4c43196f2`. This task made no new chain read. The saved response files stay private. Their file hashes were verified before use.

| Contract | Saved response file SHA256 | Runtime bytes | Runtime SHA256 | Fixture |
|---|---|---|---|---|
| Entrypoint `0xb3e6778480b2E488385E8205eA05E20060B813cb` | `619f9eadaf75b658082181ca64764d4d4d811e3daa17e6980561ecd171ab1da1` | 3251 | `da214086b3c9bc283c9fe99966baf01a5b97ad8f6f3a7313d37f89008594e1cf` | `entrypoint-runtime-block-0x6c1db44.hex` |
| Current router `0x2f84fb8982073f39ba47c7fcc29119af074abbcb` | `2e6c2968366a10247952f9575237811b5c80ccacdc8d72d0164f75e697c56b57` | 8783 | `9cf6f5c85f5f6a621badb478b91cff95c43542d695ccff90715830fa2bc2c649` | `current-router-runtime-block-0x6c1db44.hex` |
| Control: documented router `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2` | `74011bc722fc8ce17ea8373860b1620360e3546be7833dcee683b4fb8e419362` | 6381 | `de00ae5d02cf8f620781f8b6643b097096d984213adbff898d805ccb61df7282` | `published-router-runtime-block-0x6c1db44.hex` |

The entrypoint's `getRouter()` returned the current router at that block. The documented router is a different contract. It is used below only as a control for compiler behavior, never as a substitute for the current router. These reads show the code at one block. They do not show the code or router at any later block.

## 2. Metadata in the deployed code

All three contracts end with the same CBOR metadata, `a164736f6c634300081c`, plus the length `000a`. This decodes to `{"solc": 0.8.28}` and nothing else. Solidity appends only the compiler version when the metadata hash setting is `none` ([Solidity 0.8.37 metadata docs](https://docs.soliditylang.org/en/v0.8.37/metadata.html), read through Context7). The code therefore contains no hash of its source or settings. Source identity can only be shown by rebuilding the same bytes.

## 3. Public sources found

| ID | Source | Identity | Finding |
|---|---|---|---|
| R-MAIN | https://github.com/Kuru-Labs/Kuru-contracts-flow-public `main` | `70bc0c93c073f78697b99848eedefbf5dbe698c7`, tree `ea5b3cbd9ea01fde827f2cf346891d1cfa0d02c5`, committed 2026-04-15 | Pinned source. `git ls-remote` on 2026-10-14 shows it is still the `main` head. History has three commits. The root commit `24190fc81d9acef4b59a734f9205436a9e562901` (2025-11-28) differs only by a CI workflow file. |
| R-V4 | Same repository, branch `uniV4Integration` | `e3319742f79e6a69829ef33304ae39acb4f6fed3`, tree `08995440800e0d3e0d4a5aab4c72e8e2f2b9ebf9`, committed 2025-12-10 | Changes only `src/flow/KuruFlow.sol` (+139 lines) and `src/flow/KuruFlowErrors.sol` among source and settings files. Recorded as a lead only. |
| E-SCAN | https://monadscan.com/address/0x2f84fb8982073f39ba47c7fcc29119af074abbcb#code and https://monadscan.com/address/0xb3e6778480b2e488385e8205ea05e20060b813cb#code | Public pages read 2026-10-14 | Both pages offer "Verify and Publish your contract source code today!". Neither contract has verified source. Both pages say another two contracts have exactly matching bytecode, but name no address. Creator for both: `0xb624377f12d15d1647a6aAADEc8811b32A37E91E`. Router creation transaction `0x508331aa0f5bb5b789822fc66dcc67e98cf82f878e33cac993b73af4be883248`, shown as 296 days old. Entrypoint creation transaction `0x964bfa7c5185a6bcf0e3d70317370f4449fd5b98884a533e00299ae0561efa89`, shown as 344 days old. |
| E-PUB | https://monadscan.com/address/0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2#code | Public page read 2026-10-14 | Control only. "Source Code Verified [Exact Match]", contract `KuruFlowRouter`, compiler `v0.8.28+commit.7893614a`, optimization "Yes with 50 runs", EVM `cancun`, no viaIR value shown. Constructor argument `_wmon` = WMON. The verified files include `src/flow/KuruFlow.sol`, `src/flow/KuruFlowErrors.sol` and nine `lib/openzeppelin-contracts/` files. No OpenZeppelin version is shown. |
| E-SRCFY | `https://sourcify.dev/server/v2/contract/143/<address>` for all three addresses | HTTP 404, 2026-10-14T16:50:52Z | Sourcify has no record for any of the three. |
| E-VISION | https://monadvision.com/address/0x2f84fb8982073f39ba47c7fcc29119af074abbcb | HTTP 403 | Not readable without access. No result. |
| K-ADDR | https://docs.kuru.io/contracts/Contract-addresses | Read 2026-10-14 | Lists the entrypoint and the documented router `0x0d3a…FFa2`, not the current router. Lists WMON `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A`. |

No paid or keyed explorer API was used. The ages on Monadscan are relative page text, not exact timestamps. They place both deployments before the 2026-04-15 pin, and the router deployment after the R-V4 commit. Dates do not prove identity.

### Source file SHA256 at both commits

| File | R-MAIN `70bc0c9` | R-V4 `e331974` |
|---|---|---|
| `foundry.toml` | `34793c1824ff0caf592807c8cd6fa9e7208ec67ce9607c420899aca8161f1b6f` | same |
| `remappings.txt` | `ceae7349689bfb035e085b65cb24b9596be7709bfcf2cae12cafbe091f77d635` | same |
| `.gitmodules` | `03198f33e786a90d6f03b399a3d3751c7b94455a7f257cfdf18eac352ae6e292` | same |
| `src/entrypoint/KuruFlowEntrypoint.sol` | `15e19667ee20389b396a51143dccf7bbd31a701c610f1d78978c84f3b7fd1841` | same |
| `src/entrypoint/KuruFlowEntrypointTypes.sol` | `44d913012de00a2814e62f1e9c45c4408c8407c0457325de41efabecd05df1ac` | same |
| `src/flow/KuruFlow.sol` | `875adea6e7558e08bd7d8e8ab7d0eef453a3983a8aea5521d437832780b69e01` | `3b145c9913db9e64c043370cb1dd2757596b43420086c2b5957d9b91a76c2e43` |
| `src/flow/KuruFlowErrors.sol` | `ba81776e211d67f753be7ff46cd91468aa5d5f43aeb01dfd33ac9fb61ef4a621` | `f30a9675ce2ea5801f378cab34498e738463975f3f971fc00af27a7dea0d743e` |

The entrypoint file hashes equal the pins S1 and S2 in the accepted controlled-action report.

## 4. Build settings in the pinned project

`foundry.toml` at R-MAIN (and unchanged at R-V4):

| Setting | Value | Agrees with deployed code |
|---|---|---|
| `solc_version` | `0.8.28` | Yes: CBOR `solc` is `0.8.28` (`0x00081c`). |
| `bytecode_hash` | `none` | Yes: CBOR has no `ipfs` or `bzzr1` key. |
| `via_ir` | `true` | Not observable from the bytes alone. |
| `optimizer_runs` | `50` | Not observable from the bytes alone. The file does not set `optimizer`. E-PUB shows the documented router built with the optimizer on at 50 runs. |
| `evm_version` | `cancun` | Not observable from the bytes alone. |
| Libraries | None declared | Every library function used (Solady `SafeTransferLib`, OpenZeppelin `SafeERC20`, local `Approve` and `InputStream`) is internal and compiled inline. No linking is needed. |

`remappings.txt` maps `solady/`, `@openzeppelin/`, `openzeppelin-contracts/`, `openzeppelin-contracts-upgradeable/` and `forge-std/` into `lib/`. The entrypoint imports Solady `SafeTransferLib` and OpenZeppelin `IERC20`, `ReentrancyGuardTransient` and `Ownable`. The router imports OpenZeppelin `IERC20`, `SafeERC20`, `IERC20Permit` and `ReentrancyGuardTransient`.

**Missing artifact: dependency commits.** `.gitmodules` names the four `lib/` repositories, but neither commit records a submodule commit (no gitlink entries in either tree) and neither has a `foundry.lock`. Foundry records pinned dependency state in exactly those two places ([Foundry book, dependencies](https://github.com/foundry-rs/book/blob/master/src/pages/projects/dependencies.mdx), read through Context7). The exact OpenZeppelin and Solady code compiled into either contract is therefore not published. Their code is compiled into the runtime bytes, so a build with a guessed version can only test a hypothesis.

Solc build: E-PUB names `v0.8.28+commit.7893614a` for the documented router only. Solc binary hash: not recorded. No compiler was downloaded. A later granted build must record the binary's SHA256 against the official solc release list (see [REPRODUCTION.md](REPRODUCTION.md)).

## 5. Entrypoint result: `NOT_REPRODUCIBLE`

- Source: R-MAIN `src/entrypoint/KuruFlowEntrypoint.sol` and `KuruFlowEntrypointTypes.sol`. Contract name `KuruFlowEntrypoint`.
- Immutables: none in the source. The router address and owner are storage values. A rebuild would need no constructor-argument normalization in runtime code.
- Metadata: `{"solc": 0.8.28}` only. A rebuild would need no metadata normalization.
- Missing artifacts: (1) OpenZeppelin and Solady commits, see section 4. (2) Verified explorer source, see E-SCAN and E-SRCFY. (3) Any record that the deployed code came from this public file at all. The public history starts on 2025-11-28, and Monadscan shows the entrypoint as older than that.
- Matched: compiler version and metadata setting only.
- Mismatched: nothing observed. No difference was found, but no rebuild ran, so no byte was compared.
- Not built: no build ran. A build was not requested, because the pinned project does not fix its dependencies. Any build would start from a dependency guess, which the task excludes from an identity claim.

## 6. Current router result: `NOT_REPRODUCIBLE`

- Candidate sources: R-MAIN and R-V4 `src/flow/KuruFlow.sol`, contract `KuruFlowRouter`. Both are rejected by the constant check below.
- Immutable: `address public immutable WMON` set by the constructor. The deployed code pushes `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` twice with `PUSH32`. This equals the WMON address in K-ADDR. A compiled artifact would hold zero placeholders at those offsets.
- Metadata: `{"solc": 0.8.28}` only.

### Constant check

Both public versions of `KuruFlow.sol` declare these private constants (R-MAIN lines 303 and 304, R-V4 lines 354 and 355):

- `MIN_SQRT_RATIO = 4_295_128_739 + 1`, which is `0x1000276a4`.
- `MAX_SQRT_RATIO = 1_461_446_703_485_210_103_287_273_052_203_988_822_378_723_970_341 - 1`, which is `0xfffd8963efd1fc6a506488495d951d5263988d24`.

The script walks each instruction stream (push data is skipped) and counts the pushed values:

| Value | Current router | Documented router (control) |
|---|---|---|
| `0x1000276a4` (source minimum) | 2 | 1 |
| `0xfffd…988d24` (source maximum) | **0** | **1** |
| `0xfffd…988d25` (source maximum + 1) | **2** | 0 |
| WMON `0x3bd3…433a` | 2 | not counted |

The control shows that this compiler and these settings place the source value `…988d24` directly in the code. Monadscan verifies the documented router as an exact match (E-PUB). The current router never pushes `…988d24`. It pushes `…988d25` instead, which is the Uniswap `MAX_SQRT_RATIO` minus 1. Solidity evaluates a literal expression such as `…341 - 1` exactly at compile time, so neither public declaration can produce `…988d25`.

**Inference:** the current router was compiled from a source that differs from both R-MAIN and R-V4, at least in this constant. This is an observed mismatch, not proof of the full source difference. A selector or partial similarity is not identity, and none is claimed here.

- Missing artifacts: (1) the source of the deployed router, which no public commit or explorer provides; (2) the dependency commits, as for the entrypoint; (3) verified explorer source.
- Matched: compiler version, metadata setting and the minimum constant.
- Mismatched: the maximum constant, as above.
- Not built: no build ran. A build of R-MAIN or R-V4 cannot match, because of the constant mismatch.

## 7. Effect on P21

What this narrows:

- The deployed entrypoint and the current router have no verified or reproducible public source today. Any P21 argument that relies on the public router source to describe the current router's behavior is unsupported. Item 5 of the accepted report stays open, now with exact missing artifacts.
- The public router source must not be used to reason about the current router. The current router holds at least one value that no public version contains.
- The entrypoint source is consistent with the deployed compiler settings, but its dependency code is unknown. Its pinned-source properties (mutable router, owner control, fees up to 100%, no swap deadline) stay unconfirmed for the deployed code.

What stays unresolved, unchanged by this task:

- The owner can replace the router at any time. One block's `getRouter()` value does not bind a later action.
- Gas bounds, action expiry, Privy policy field support (`data`, `type`, `authorization_list`, gas fields, nested tuple paths), EIP-7702 delegation binding, policy administration separation and the missing signer, quote and broadcast clients.
- Privy reconciliation stays blocked by HTTP 403 (Cloudflare 1010). This task infers nothing about policy field support.

## 8. Ways to close the gap (not adopted)

These are options for a controller or builder decision. None is authorized by this report.

1. Ask Kuru for the exact source, dependency commits and build command of both contracts, or for verified explorer source.
2. E-PUB holds verified OpenZeppelin files used by the documented router. They are a primary candidate for the OpenZeppelin part of a dependency hypothesis, not proof of the entrypoint's version. Solady stays unknown.
3. Find the two other contracts that Monadscan says share each bytecode. Verified source there would be a primary artifact. This needs an explorer feature that does not require a key, or a separate approval.
4. With a capacity grant, build the entrypoint from R-MAIN with a stated dependency hypothesis. An exact byte match would then be a strong but conditional result, reported with that hypothesis. A mismatch would stay a mismatch.
