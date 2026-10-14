# Kuru Flow deployed source identity

Task `P21-DEPLOYED-SOURCE-L3-20261014-LOCAL-v1`, a bounded source-identity prerequisite for P21 #20 and issue #58. Base `98d89c5f41d48ce5f76051606e5fba0b767a9f3d`. Sources checked 2026-10-14.

Stage: public-source research and local byte checks only. This task made no new RPC, provider, explorer-API-key, quote, wallet, signing, broadcast, funding or credential request. It ran no compiler, downloaded no compiler and installed no dependency.

## Answer

| Contract | Address on Monad `143` at block `0x6c1db44` | Result |
|---|---|---|
| Kuru Flow entrypoint | `0xb3e6778480b2E488385E8205eA05E20060B813cb` | **`NOT_REPRODUCIBLE`.** The public source and compiler settings are known. The OpenZeppelin and Solady dependency commits are not published, and no explorer holds verified source. |
| Current router (`getRouter()`) | `0x2f84fb8982073f39ba47c7fcc29119af074abbcb` | **`NOT_REPRODUCIBLE`.** No public source is known. A constant in the deployed code differs from both public versions of `KuruFlow.sol`, so neither public commit is its source. |

Neither result is an exact identity. Neither result qualifies P21 or any execution step. Details and evidence are in [SOURCE_IDENTITY.md](SOURCE_IDENTITY.md). The checks a reviewer can repeat, and the build recipe for a later granted attempt, are in [REPRODUCTION.md](REPRODUCTION.md).

## Files

| File | Content |
|---|---|
| [SOURCE_IDENTITY.md](SOURCE_IDENTITY.md) | Inputs, sources, settings, matches, mismatches, missing artifacts and P21 effect. |
| [REPRODUCTION.md](REPRODUCTION.md) | Commands that repeat every local check, and the frozen recipe for a later build. |
| `entrypoint-runtime-block-0x6c1db44.hex` | Deployed entrypoint runtime code, 3251 bytes. |
| `current-router-runtime-block-0x6c1db44.hex` | Deployed current-router runtime code, 8783 bytes. |
| `published-router-runtime-block-0x6c1db44.hex` | Deployed code of the documented router `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2`, 6381 bytes. Used only as a control. It is not the current router. |
| `scripts/kuru_deployed_source/compare_bytecode.py` | Standard-library fixture check, constant count and exact byte comparison. |
| `tests/kuru_deployed_source/test_compare_bytecode.py` | Self-check, including known-equal and one-byte-different controls. |

The fixtures are the exact `result` strings of the three `eth_getCode` responses from the builder-approved read-only chain check of 2026-10-14. They hold public chain data only.

## Source-gap history

This note amends item 5 ("Deployed identity") of section 1 in [the accepted controlled-action report](../controlled-action-feasibility/CONTROLLED_ACTION_FEASIBILITY.md#1-answer). That report stays unchanged. The approved chain check found the current router and the deployed code. This task found that neither contract can be reproduced from public sources today. It also found evidence that the current router was not built from the public router source.
