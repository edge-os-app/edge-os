# Direct Kuru Flow route without the Kuru quote API

Status: local implementation and read-only simulation. No actual release is registered. No trade, signature or send follows from this document.

## Why this route exists

The Kuru Flow quote API `ws.kuru.io` accepted TCP connections and returned no bytes on every path during the builder's route check. The on-chain Flow contracts still work. The builder approved a direct call to the Flow entrypoint with a one-pool program that this repository builds from release fields.

The builder's read-only simulation used `eth_call` with temporary state overrides. It signed nothing and sent nothing. Raw results are in `.scratch/direct-route-l1-20261022/evidence/`:

- `DIRECT_ROUTE_SIM_FINDINGS1.md`
- `DIRECT_ROUTE_SIM1.json`
- `DIRECT_ROUTE_SIM2.json`
- `direct_route_sim1.py`
- `fee_search.py`

## Pinned facts

| Item | Value |
| --- | --- |
| Flow entrypoint | `0xb3e6778480b2E488385E8205eA05E20060B813cb` |
| Method | `executeSwap(SwapIntent,FeeCollection,bytes)` |
| Selector | `0xce1e7030` |
| Pool | `0x97199b34564911936bc850ac45ede785892b5aad` (nad.fun pair) |
| Token 0 | WMON `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` |
| Token 1 | MOE `0xd8e004acba279417c04c0633cb5a21ceca207777` |
| Direction byte | `0x00` = token0 to token1 |
| Program fee field | 16000 ppm is the lowest value that passed the simulation |
| Program source | Kuru `KuruFlow.sol`, Kuru-contracts-flow-public commit `70bc0c93c0` |

The one-hop program layout is:

```text
0x02 | input token (20 bytes) | 0x01 | 0xffff | 0x00 | pool (20 bytes) | direction (1 byte) | fee (3 bytes, ppm)
```

Example program with a 16000 ppm fee:

```text
0x023bd359c1119da7da1d913d1c4d2b7c461115433a01ffff0097199b34564911936bc850ac45ede785892b5aad00003e80
```

## Fee and output findings

Fee fields from 0 to 10000 ppm reverted with `NadFunPair: K`. The program fee field was lower than the pair's real fee. The lowest passing value was 16000 ppm. With 16000 ppm, 50 WMON gave 3784.893 MOE in the simulation. That result equals the local constant-product formula:

```text
out = in * (1e6 - fee) * reserve_out / (reserve_in * 1e6 + in * (1e6 - fee))
```

The implementation reads `getReserves()` once on the pinned pool at the latest block. It uses the formula above and refuses before signing when the slippage bound falls below the approved minimum. It never changes the approved minimum.

## Local controls

- The release selects `quote.source = "DIRECT_V2_PROGRAM"`.
- The release pins the pool, token order, direction byte, program fee, approved program hex and the read-only `/rpc` endpoint.
- Release validation rebuilds the program from those pins and refuses any mismatch.
- Calldata is built locally from release fields only: approved output/input tokens, approved input, approved minimum, zero fees and the approved program.
- The direct source uses no bearer token and no Kuru credential.
- One read counts as the one `quote_requests` slot.
- Evidence classes and the empty actual release and binding registries are unchanged.

## Incident note

The builder pasted the Kuru incident report of 2026-09-02. It affected the orderbook and MarginAccount. The aggregator (Flow) was not affected. This route uses neither the orderbook nor MarginAccount. Keep exact-amount approval, revoke to zero after the action, and re-read the router before use.

## Remaining limits

This route is implemented, not qualified. An actual release needs the controller's unfunded policy proof, builder funding approval, a registered server-owned release and binding, and the separate operation authority. Local tests use synthetic replies. They do not prove live reserve behavior, mempool ordering, finality or provider availability.
