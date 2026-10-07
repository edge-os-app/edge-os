# P15 offline contract checks

`fixtures.json` contains invented, synthetic examples. `check_contract.py` checks cross-agent ownership, same-token position identity, exact preview binding, unknown submission handling, removal and renewal, scoped stops, allowance arithmetic, weighted average cost, capital flows, and monitoring fields.

Run from the repository root:

```sh
python3 -B docs/contracts/p15/check_contract.py
```

The checker uses only Python's standard library. It makes no network calls and reads no environment values. It does not implement or qualify wallet, signer, policy, storage, or transaction enforcement.
