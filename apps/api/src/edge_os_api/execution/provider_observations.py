"""Bounded observations. Missing provider contracts and finality stay unavailable."""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from edge_os_api.execution.operating_release import BoundRelease

from edge_os_api.core.provider_ports import ProviderUnavailable, RemovalStatus
from edge_os_api.execution.current_holdings import HoldingsObservation, HoldingsUnavailable, read_rpc_holdings
from edge_os_api.execution.original_transaction import RpcClient, token_of, validate_signed
from edge_os_api.funding.observation import DepositObservation, ObservationUnavailable

_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_QUANTITY = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)")


def _quantity(value: Any) -> int | None:
    return int(value, 16) if type(value) is str and len(value) <= 66 and _QUANTITY.fullmatch(value) else None


@dataclass(frozen=True)
class GasChargeObservation:
    state: str
    reason: str | None
    evidence_class: str
    transaction_hash: str | None = None
    block_number: int | None = None
    block_hash: str | None = None
    gas_limit: int | None = None
    gas_used: int | None = None
    price_per_gas: int | None = None
    raw: str | None = None


def observe_monad_charge(*, original: Mapping[str, Any], receipt: Mapping[str, Any],
                         canonical_block: Mapping[str, Any], finalized_block: Mapping[str, Any],
                         evidence_class: str, finality_qualified: bool,
                         binding: BoundRelease | None = None,
                         synthetic_bindings: Mapping[str, str] | None = None) -> GasChargeObservation:
    """Bind a documented gas-limit charge to exact original signed bytes and finalized block identity.

    This pure reading is not the mounted original receipt settlement. An actual qualified finality source
    and release still belong to Phase B. Synthetic evidence can never produce an ACTUAL result here.
    """
    reason = "GAS_BINDING_UNAVAILABLE"
    result = None
    try:
        bound_class = (None if binding is None else binding.qualify_original(
            original, synthetic_bindings=synthetic_bindings))
        qualified = (bound_class == evidence_class if binding is not None else
                     finality_qualified is True and evidence_class == "SYNTHETIC_FIXTURE")
        if evidence_class not in ("SYNTHETIC_FIXTURE", "PROVIDER_UNQUALIFIED", "PROVIDER_ACTUAL"):
            reason = "GAS_EVIDENCE_INVALID"
        elif not qualified:
            reason = "FINALITY_UNQUALIFIED"
        else:
            unsigned = original["unsigned"]
            fields = ("type", "chain_id", "nonce", "value", "gas_limit", "max_fee_per_gas", "max_priority_fee_per_gas")
            if (not isinstance(unsigned, Mapping) or set(unsigned) != {*fields, "to", "data"}
                    or not all(type(unsigned.get(x)) is int and 0 <= unsigned[x] < 2**256 for x in fields)
                    or type(unsigned["to"]) is not str or _ADDRESS.fullmatch(unsigned["to"]) is None
                    or type(unsigned["data"]) is not str or re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", unsigned["data"]) is None
                    or unsigned["type"] != 2):
                reason = "ORIGINAL_GAS_UNAVAILABLE"
            else:
                tx_hash, errors = validate_signed(original["signed_bytes"], unsigned, original["wallet_address"])
                limit, cap, priority = (unsigned[x] for x in ("gas_limit", "max_fee_per_gas", "max_priority_fee_per_gas"))
                number, boundary = _quantity(receipt.get("blockNumber")), _quantity(finalized_block.get("number"))
                price, used = _quantity(receipt.get("effectiveGasPrice")), _quantity(receipt.get("gasUsed"))
                base = _quantity(canonical_block.get("baseFeePerGas"))
                block_hash = receipt.get("blockHash")
                bound = (not errors and tx_hash == original["transaction_hash"] == receipt.get("transactionHash")
                    and type(original.get("chain_id")) is int and original["chain_id"] == unsigned.get("chain_id") == 143
                    and receipt.get("from", "").lower() == original["wallet_address"].lower()
                    and receipt.get("to", "").lower() == unsigned["to"].lower()
                    and type(block_hash) is str and _HASH.fullmatch(block_hash) is not None
                    and type(finalized_block.get("hash")) is str and _HASH.fullmatch(finalized_block["hash"]) is not None
                    and number is not None and number == _quantity(canonical_block.get("number"))
                    and boundary is not None and number <= boundary and block_hash == canonical_block.get("hash")
                    and (number != boundary or block_hash == finalized_block["hash"])
                    and receipt.get("status") in ("0x0", "0x1"))
                if not bound:
                    reason = "GAS_IDENTITY_OR_FINALITY_MISMATCH"
                elif (limit <= 0 or price is None or used is None or used > limit or base is None or base > cap
                      or priority > cap or price != min(base + priority, cap)):
                    reason = "GAS_PRICE_OR_LIMIT_UNAVAILABLE"
                else:
                    result = GasChargeObservation("OBSERVED", None, evidence_class, tx_hash, number, block_hash,
                                                  limit, used, price, str(limit * price))
    except Exception:
        pass
    return result or GasChargeObservation("UNAVAILABLE", reason, evidence_class if evidence_class == "SYNTHETIC_FIXTURE" else "UNQUALIFIED")


class RpcHoldingsObserver:
    """Reuse the accepted finalized holdings reader for one frozen wallet and asset set."""

    def __init__(self, *, observer: RpcClient, wallet_address: str, chain_id: int,
                 assets: list[tuple[str, int]], source: str, evidence_class: str,
                 clock: Callable[[], dt.datetime], finality_qualified: bool = False,
                 binding: BoundRelease | None = None, synthetic_bindings: Mapping[str, str] | None = None) -> None:
        if (type(wallet_address) is not str or not _ADDRESS.fullmatch(wallet_address)
                or type(chain_id) is not int or chain_id not in (143, 10143)
                or type(source) is not str or re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", source) is None
                or evidence_class not in ("SYNTHETIC_FIXTURE", "PROVIDER_UNQUALIFIED", "PROVIDER_ACTUAL")
                or (evidence_class == "PROVIDER_ACTUAL" and binding is None) or type(finality_qualified) is not bool):
            raise ValueError("HOLDINGS_BINDING_INVALID")
        invalid = False
        try:
            seen = set()
            for asset, decimals in assets:
                token = token_of(asset)
                network = "monad:143" if chain_id == 143 else "monad-testnet:10143"
                if (type(asset) is not str or not asset.startswith(network + "/") or asset in seen
                        or (token is None and asset != network + "/native")
                        or (token is not None and _ADDRESS.fullmatch(token) is None)
                        or type(decimals) is not int or not 0 <= decimals <= 255):
                    invalid = True
                seen.add(asset)
            invalid = invalid or not assets
        except Exception:
            invalid = True
        if invalid:
            raise ValueError("HOLDINGS_ASSETS_INVALID")
        if binding is not None:
            release = binding.release.content()
            allowed = {(release["route"][leg]["asset_id"], release["route"][leg]["decimals"])
                       for leg in ("input_asset", "output_asset")} | {("monad:143/native", 18)}
            if (wallet_address != release["wallet_address"] or chain_id != 143 or source != release["observer"]["destination_id"]
                    or evidence_class != release["evidence_class"] or not set(map(tuple, assets)) <= allowed):
                raise ValueError("HOLDINGS_RELEASE_MISMATCH")
        self._observer, self._wallet, self._chain, self._assets = observer, wallet_address, chain_id, tuple((asset, decimals) for asset, decimals in assets)
        self._source, self._evidence, self._clock, self._qualified = source, evidence_class, clock, finality_qualified
        self._binding = binding
        self._synthetic_bindings = None if synthetic_bindings is None else dict(synthetic_bindings)

    def read(self) -> HoldingsObservation:
        """Return complete fresh bound holdings, or a stable unavailable error with no provider detail."""
        if self._binding is None and (not self._qualified or self._evidence != "SYNTHETIC_FIXTURE"):
            raise HoldingsUnavailable("HOLDINGS_FINALITY_UNQUALIFIED")
        result = None
        reason = "HOLDINGS_UNAVAILABLE"
        try:
            selected: dict[str, Any] = {}
            observer = self._observer
            if self._binding is not None:
                self._binding.admit(self._binding.identity(), now=self._clock(), synthetic_bindings=self._synthetic_bindings)
                class BoundObserver:
                    def call(self, method: str, params: list[Any]) -> Any:
                        if method in ("eth_call", "eth_getBalance") and params[-1] != selected.get("number"):
                            raise ValueError("holdings block mismatch")
                        value = observer.call(method, params)
                        if method == "eth_getBlockByNumber":
                            if (params != ["finalized", False] or not isinstance(value, Mapping)
                                    or type(value.get("hash")) is not str or not _HASH.fullmatch(value["hash"])):
                                raise ValueError("finality unavailable")
                            selected.update(value)
                        return value
                reader = BoundObserver()
            else:
                reader = observer
            observed = read_rpc_holdings(reader, wallet_address=self._wallet, assets=list(self._assets),
                                         source=self._source, evidence_class=self._evidence)
            now = self._clock()
            if not isinstance(now, dt.datetime) or now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
                reason = "HOLDINGS_CLOCK_UNAVAILABLE"
            else:
                reason = observed.refusal(wallet_address=self._wallet, chain_id=self._chain, now=now)
                if reason is None:
                    if self._binding is not None:
                        self._binding.admit(self._binding.identity(), now=now, synthetic_bindings=self._synthetic_bindings)
                        observed = replace(observed, source=self._source + ":" + selected["hash"])
                    result = observed
        except Exception:
            pass
        if result is None:
            raise HoldingsUnavailable(reason or "HOLDINGS_UNAVAILABLE")
        return result


class UnqualifiedDepositObserver:
    """No accepted provider deposit schema binds a declared original reference and effect yet."""

    def observe(self, wallet_id: str, network_id: int) -> list[DepositObservation]:
        raise ObservationUnavailable("DEPOSIT_ORIGINAL_REFERENCE_SCHEMA_UNQUALIFIED")


class UnqualifiedRemovalObserver:
    """No accepted exact owner/wallet/signer metadata readback contract yet."""

    def observe(self, *, agent_id: str, wallet_id: str, network_id: str) -> RemovalStatus:
        raise ProviderUnavailable("REMOVAL_OWNER_WALLET_SIGNER_SCHEMA_UNQUALIFIED")
