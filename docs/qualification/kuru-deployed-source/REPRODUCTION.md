# Reproduction: Kuru Flow deployed source checks

Task `P21-DEPLOYED-SOURCE-L3-20261014-LOCAL-v1`. These steps repeat every local check behind [SOURCE_IDENTITY.md](SOURCE_IDENTITY.md). They need Python 3.11 or later and `git`. They make no chain, provider or explorer request.

## 1. Local checks (run on 2026-10-14)

Run from the repository root.

```sh
python3 -m unittest tests.kuru_deployed_source.test_compare_bytecode -v
```

Result on 2026-10-14 with Python 3.14.4: 13 tests passed in 0.009 s. The tests:

- reject malformed fixtures and a truncated `PUSH` instruction;
- confirm that push data is skipped when values are counted;
- compare a fixture with itself (known-equal control) and with a copy that has byte 4000 changed (one-byte-different control);
- pin the length, SHA256 and metadata of each fixture, and the constant counts in section 6 of SOURCE_IDENTITY.md.

The same facts from the command line:

```sh
python3 scripts/kuru_deployed_source/compare_bytecode.py inspect \
  docs/qualification/kuru-deployed-source/current-router-runtime-block-0x6c1db44.hex \
  --sha256 9cf6f5c85f5f6a621badb478b91cff95c43542d695ccff90715830fa2bc2c649 --length 8783 \
  --constant 1000276a4 \
  --constant fffd8963efd1fc6a506488495d951d5263988d24 \
  --constant fffd8963efd1fc6a506488495d951d5263988d25 \
  --constant 3bd359c1119da7da1d913d1c4d2b7c461115433a

python3 scripts/kuru_deployed_source/compare_bytecode.py inspect \
  docs/qualification/kuru-deployed-source/published-router-runtime-block-0x6c1db44.hex \
  --sha256 de00ae5d02cf8f620781f8b6643b097096d984213adbff898d805ccb61df7282 --length 6381 \
  --constant 1000276a4 \
  --constant fffd8963efd1fc6a506488495d951d5263988d24 \
  --constant fffd8963efd1fc6a506488495d951d5263988d25

python3 scripts/kuru_deployed_source/compare_bytecode.py inspect \
  docs/qualification/kuru-deployed-source/entrypoint-runtime-block-0x6c1db44.hex \
  --sha256 da214086b3c9bc283c9fe99966baf01a5b97ad8f6f3a7313d37f89008594e1cf --length 3251
```

`inspect` exits 0 and prints JSON when the fixture matches the given length and SHA256. It exits 2 with an error on any mismatch or malformed input.

Fixture file SHA256 (the text files, including their trailing newline):

| Fixture | SHA256 |
|---|---|
| `entrypoint-runtime-block-0x6c1db44.hex` | `b7688f5261bebfb3f3ed8c3e443610175546f044fcd5aa0491cc118f48dd5ee7` |
| `current-router-runtime-block-0x6c1db44.hex` | `874ebeec8086d33684b0b7dcfa68aac43d8935ae8c6187524e99af5b9a0321b9` |
| `published-router-runtime-block-0x6c1db44.hex` | `10535f35b166521156121f6bcd013aeb4abdefbabb173e37b7aa49579a6546a7` |

## 2. Source checks

```sh
git init kuru-flow && cd kuru-flow
git remote add origin https://github.com/Kuru-Labs/Kuru-contracts-flow-public.git
git fetch --depth 1 origin 70bc0c93c073f78697b99848eedefbf5dbe698c7 e3319742f79e6a69829ef33304ae39acb4f6fed3
git ls-tree -r 70bc0c93c073f78697b99848eedefbf5dbe698c7 | grep 160000   # no output: no submodule commits
git ls-tree -r e3319742f79e6a69829ef33304ae39acb4f6fed3 | grep 160000   # no output
git cat-file -e 70bc0c93c073f78697b99848eedefbf5dbe698c7:foundry.lock   # fails: no lock file
git show 70bc0c93c073f78697b99848eedefbf5dbe698c7:src/flow/KuruFlow.sol | sed -n 303,304p
git show e3319742f79e6a69829ef33304ae39acb4f6fed3:src/flow/KuruFlow.sol | sed -n 354,355p
```

Compare the printed `git show <commit>:<file> | shasum -a 256` values with section 3 of SOURCE_IDENTITY.md.

## 3. Frozen recipe for a later build (not run)

No build ran in this task. A build needs a separate, finite controller capacity grant. The pinned project cannot fix its own dependency commits, so any build below is a hypothesis test, never an identity claim by itself.

Only one target is useful today: the entrypoint from R-MAIN. A build of `KuruFlowRouter` from R-MAIN or R-V4 cannot match the current router, because of the constant mismatch in section 6.

1. Fetch R-MAIN at `70bc0c93c073f78697b99848eedefbf5dbe698c7` into a private scratch directory.
2. Record a written dependency hypothesis before any build: an exact OpenZeppelin commit and an exact Solady commit, each with its reason. One justified candidate for OpenZeppelin is the version whose files equal the nine verified files on the E-PUB page. Solady has no primary evidence.
3. Place each dependency at its recorded commit under `lib/`. Record each commit and the tree hash.
4. Use solc `0.8.28+commit.7893614a` from the official release list. Record the binary path and SHA256, and check it against the published release hash.
5. Build with the project's own settings and no setting overrides: `forge build --offline --use <solc path> --skip test script`. `--offline` prevents a compiler download. Record the Forge version, the resolved compiler settings from the artifact `metadata`, and the full command output with timing. `foundry.toml` does not set `optimizer`, and this task did not verify the Forge default for that flag. If the resolved settings show the optimizer off, the one permitted settings repair build adds `--optimize true`, justified by E-PUB ("Yes with 50 runs").
6. Write `out/KuruFlowEntrypoint.sol/KuruFlowEntrypoint.json` field `deployedBytecode.object` to a fixture file in the same `0x` hex format.
7. Run `python3 scripts/kuru_deployed_source/compare_bytecode.py compare docs/qualification/kuru-deployed-source/entrypoint-runtime-block-0x6c1db44.hex <artifact.hex>`. Exit 0 means `EXACT_MATCH`; exit 1 means `MISMATCH` with the first differing offset.

The entrypoint has no immutables and its metadata holds only the compiler version, so no normalization applies. Any difference stays a mismatch. One settings repair build is permitted only with a written reason drawn from primary evidence. No search over versions or settings is permitted.
