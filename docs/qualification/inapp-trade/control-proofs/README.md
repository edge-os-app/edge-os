# In-app trade control proofs and decisions

`CONTROL-ADOPT-L1-20261026`. This directory holds the evidence that the in-app release controls cite. It grants
no trade, signing or provider authority.

## Tree

```text
control-proofs/
  proofs-4/                         seven proof artifacts and controls.json (2026-10-23/26 run)
  proofs-5/                         the same seven, byte for byte, plus opaque_program.proof.json
  stores/privy-store-1/             the Privy outcome and capture records of the control packet
  stores/privy-store-1.expiry-rerun/ the one expiry-row re-run
  stores/chain-store-1/chain_results.json  the read-only Monad records
```

## Frozen hashes

`proofs-4`:

| File | SHA-256 |
| --- | --- |
| `controls.json` | `9182273d304f1ebea0268a7151d7cfb9709ae89cda7929ae8861378d7129c8f1` |
| `expiry_freshness.proof.json` | `c638035f9f5d42651b53da6d7082ea0e3ec6b1f70db5e76781ce347c1d92b5e7` |
| `fees.proof.json` | `6232e2a96d9623fa7a442dc36bdb8f467085805ee685adf9b8ada314bcbf1675` |
| `gas_action_capacity.proof.json` | `f5a5e82b8edd172c8beb798de26b2c117344ec6879b248be5504a36d0f3d7e29` |
| `input_output_assets.proof.json` | `b7c303f625ff3a094c79f81f004fb5a65bdb81599a5a495faafc919292164c33` |
| `minimum_output.proof.json` | `0dcee961871eb38e76079747cd5ffdf55956ed580ffc97e663d2ba8d7b5d94da` |
| `raw_input.proof.json` | `82c542a72664efd5d4a83bc674be8d6fc45e976538fe8b65bcf36945192cf40c` |
| `recipient.proof.json` | `4eaa956243fd0d92d767f73620e89b5685538b34bd4c7bab77259f0d17efc8bb` |

`proofs-5` adds:

| File | SHA-256 |
| --- | --- |
| `opaque_program.proof.json` | `c172e1d574c168d72b4dad9e7a7f3c6d8112be4f7d99c7a28ef3210536380997` |
| `controls.json` | `06749a3efd7122a18d75e6ddae7c5a6da6e5790a475b38697ecf448fdabb2da7` |

The seven artifact files in `proofs-5` are byte-identical to `proofs-4`. `tests/execution/test_inapp_trade_release.py`
checks this, and `tests/privy_unfunded_proof` rebuilds the artifacts from the committed stores.

## Build command

From the repository root, with no network:

```sh
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -B -s -m scripts.privy_unfunded_proof.control_proofs \
  --authored docs/qualification/inapp-trade/release.authored.json \
  --privy-store docs/qualification/inapp-trade/control-proofs/stores/privy-store-1 \
  --chain-store docs/qualification/inapp-trade/control-proofs/stores/chain-store-1 \
  --with-expiry-rerun --out <new directory>
```

The command refuses an existing output directory. The committed `proofs-5` is the reviewed output of this
command.

## Secret check

Checked before the commit:

- The only URL is the public Privy signing endpoint
  `https://api.privy.io/v1/wallets/bsb2feecuxl81dl5jz4u9xxo/rpc` in the intent records. It carries no user-info,
  no query and no key. The chain store holds no URL.
- The stores hold no `Authorization` header, no `Bearer` value, no API key, no app secret, no private key and no
  PEM block. One literal `Authorization` text match is the claim text `privy-authorization-signature` in
  `expiry_freshness.proof.json`; it is not a credential.
- The raw stores hold no request headers, no signed bytes and no key material. The four `ALLOW` outcomes in the
  v3 store carry only `signed_bytes_sha256`; the store holds no signed bytes.

## Scope and limits

- The artifacts are only as authentic as the committed stores. The chain records can be re-checked at block
  `115860413` on an archive node. The Privy records cannot be re-created; the stored outcome and capture records
  are the evidence.
- The chain simulations prove the deployed code at one block. The router is owner-mutable; the release's
  `mutable_router_proof_sha256` and its pre-run recheck cover later blocks.
- The storage overrides fund the simulation only. They prove nothing about the live wallet.
- `opaque_program` is a builder decision, not a provider proof. The host exact program check is `LOCAL_TESTED`.
  The trace is one block. Proxy implementations are observed and owner-upgradeable.
- Control 11 covers the provider-side signing cutoff only. Control 4 covers the input side. Control 8 covers the
  fee sum bound. Control 6 pins the observed fee recipients and their bounds. The release document states each
  limit.
