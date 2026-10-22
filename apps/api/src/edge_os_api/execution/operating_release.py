"""Pure immutable financial authority. No actual release is approved or mounted."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from edge_os_api.research_history.http_clients.client_config import validate_endpoint
from edge_os_api.kuru_flow.types import ApprovedAdapterConfiguration, canonical_bytes, canonical_raw, parse_utc

SCHEMA = "edge-os.controlled-execution-release/1"
CONTROLS = frozenset({"chain", "wallet_signer_binding", "entrypoint_method", "input_output_assets", "raw_input",
    "recipient", "minimum_output", "fees", "approvals", "gas_action_capacity", "expiry_freshness", "opaque_program"})
APPROVED_ACTUAL_RELEASES: Mapping[str, str] = MappingProxyType({})
APPROVED_ACTUAL_BINDINGS: Mapping[str, str] = MappingProxyType({})
_FIELDS = frozenset({"release_id", "kind", "evidence_class", "purpose", "chain_id", "wallet_id", "wallet_address",
    "signer_id", "policy_id", "policy_owner_id", "policy_content_sha256", "independent_proof_sha256", "deployment",
    "route", "quote", "broadcast", "observer", "gas", "transaction", "limits", "valid_until", "finality", "controls"})


class ReleaseRefused(ValueError):
    """A stable pre-I/O admission refusal."""


def _require(condition: bool) -> None:
    if not condition:
        raise ReleaseRefused("EXECUTION_RELEASE_INVALID")


def _text(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9._:/-]{1,200}", value) is not None and value.upper() not in {
        "UNKNOWN", "UNSET", "UNSUPPORTED", "NONE", "NULL", "PLACEHOLDER"}


def _hash(value: Any, length: int = 64) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None


def _json_domain(value: Any, depth: int = 0) -> None:
    _require(depth <= 16)
    if type(value) is dict:
        _require(len(value) <= 64 and all(type(key) is str for key in value))
        for item in value.values():
            _json_domain(item, depth + 1)
    elif type(value) is list:
        _require(len(value) <= 128)
        for item in value:
            _json_domain(item, depth + 1)
    else:
        _require(value is None or type(value) is bool or (type(value) is int and 0 <= value < 2**256)
                 or (type(value) is str and len(value) <= 32768))


def _validate(value: dict[str, Any]) -> None:
    _require(set(value) == _FIELDS)
    _json_domain(value)
    _require(value["kind"] in ("SYNTHETIC_FIXTURE", "ACTUAL") and value["purpose"] == "CONTROLLED_ONE_ACTION_QUALIFICATION")
    _require(value["evidence_class"] == ("SYNTHETIC_FIXTURE" if value["kind"] == "SYNTHETIC_FIXTURE" else "PROVIDER_ACTUAL"))
    _require(all(_text(value[x]) for x in ("release_id", "wallet_id", "signer_id", "policy_id", "policy_owner_id")))
    _require(value["policy_owner_id"] != value["signer_id"])
    _require(all(_hash(value[x]) for x in ("policy_content_sha256", "independent_proof_sha256")))
    route = ApprovedAdapterConfiguration.model_validate(value["route"])
    _require(type(value["chain_id"]) is int and value["chain_id"] == route.chain_id == 143)
    _require(route.recipient == value["wallet_address"] and int(route.recipient, 16) != 0)
    _require(not route.input_is_native() and not route.output_asset.is_native())
    for asset in (route.input_asset, route.output_asset):
        _require(asset.asset_id.lower() == f"monad:143/{asset.token_address.lower()}")
    _require(route.input_asset.token_address.lower() != route.output_asset.token_address.lower())
    _require(int(route.approved_input_raw) > 0 and int(route.approved_input_raw) < 2**256
             and int(route.approved_min_output_raw) > 0 and int(route.approved_min_output_raw) < 2**256
             and route.approved_allowance_raw == route.approved_input_raw
             and route.supported_schema_variants == ["TRANSACTION_CALLDATA"])
    freshness = value["route"]["freshness"]
    _require(set(freshness) == {"max_quote_age_seconds", "max_input_age_seconds", "intent_expires_at", "mandate_expires_at"})
    _require(all(type(freshness[x]) is int and freshness[x] > 0 for x in ("max_quote_age_seconds", "max_input_age_seconds")))
    expiry = parse_utc(value["valid_until"])
    _require(expiry <= parse_utc(freshness["intent_expires_at"]) <= parse_utc(freshness["mandate_expires_at"]))
    deployment = value["deployment"]
    _require(set(deployment) == {"source_commit", "entrypoint_code_sha256", "router_address", "router_code_sha256", "abi_sha256", "mutable_router_proof_sha256"})
    _require(_hash(deployment["source_commit"], 40) and all(_hash(deployment[x]) for x in (
        "entrypoint_code_sha256", "router_code_sha256", "abi_sha256", "mutable_router_proof_sha256")))
    _require(type(deployment["router_address"]) is str and re.fullmatch(r"0x[0-9a-fA-F]{40}", deployment["router_address"]) is not None)
    quote = value["quote"]
    _require(type(quote) is dict)
    source = quote.get("source", "KURU_API")
    _require(source in ("KURU_API", "DIRECT_V2_PROGRAM"))
    _require(type(quote["slippage_bps"]) is int and 1 <= quote["slippage_bps"] <= 10000)
    if source == "KURU_API":
        _require(set(quote) == {"endpoint", "credential_slot", "slippage_bps"}
                 or set(quote) == {"source", "endpoint", "credential_slot", "slippage_bps"})
        _require(_text(quote["credential_slot"]))
        _require(urlsplit(quote["endpoint"]).path == "/api/quote")
    else:
        _require(set(quote) == {"source", "endpoint", "slippage_bps", "pool_address", "token0_address",
                                "token1_address", "direction", "program_fee_ppm"})
        _require(all(type(quote[x]) is str and re.fullmatch(r"0x[0-9a-fA-F]{40}", quote[x])
                     for x in ("pool_address", "token0_address", "token1_address")))
        _require(type(quote["direction"]) is int and quote["direction"] in (0, 1))
        _require(type(quote["program_fee_ppm"]) is int and 0 < quote["program_fee_ppm"] < 10**6)
        _require(urlsplit(quote["endpoint"]).path == "/rpc")
        _require(route.selector.lower() == "0xce1e7030" and route.method == "EXECUTE_SWAP")
        _require(quote["token0_address"].lower() != quote["token1_address"].lower())
        from edge_os_api.execution.direct_route_quote_client import build_program_hex
        expected0, expected1 = ((route.input_asset.token_address, route.output_asset.token_address)
                                if quote["direction"] == 0
                                else (route.output_asset.token_address, route.input_asset.token_address))
        _require(quote["token0_address"].lower() == expected0.lower()
                 and quote["token1_address"].lower() == expected1.lower())
        _require(build_program_hex(input_token=route.input_asset.token_address,
                                   pool_address=quote["pool_address"], direction=quote["direction"],
                                   fee_ppm=quote["program_fee_ppm"]).lower()
                 == route.approved_program_hex.lower())
    for role in ("broadcast", "observer"):
        destination = value[role]
        _require(set(destination) == {"role", "destination_id", "endpoint", "credential_slot"}
                 and destination["role"] == role and _text(destination["destination_id"]) and _text(destination["credential_slot"]))
    _require(value["broadcast"]["endpoint"] != value["observer"]["endpoint"]
             and value["broadcast"]["destination_id"] != value["observer"]["destination_id"])
    limits = value["limits"]
    _require(set(limits) == {"actions", "attempts", "broadcasts", "quote_requests", "signer_requests", "observer_requests",
        "max_request_bytes", "max_response_bytes", "deadline_seconds"})
    _require(all(type(x) is int and x > 0 for x in limits.values()))
    _require(all(limits[x] == 1 for x in ("actions", "attempts", "broadcasts", "quote_requests", "signer_requests")))
    for endpoint in (quote["endpoint"], value["broadcast"]["endpoint"], value["observer"]["endpoint"]):
        validate_endpoint(endpoint)
        parts = urlsplit(endpoint)
        _require(parts.scheme == "https" and not parts.query and parts.path in ("/api/quote", "/rpc"))
        _require((parts.hostname.endswith(".invalid")) == (value["kind"] == "SYNTHETIC_FIXTURE"))
    transaction = value["transaction"]
    _require(set(transaction) == {"type", "value_raw", "signer_method", "request_expires_at"}
             and type(transaction["type"]) is int and transaction["type"] == 2 and transaction["value_raw"] == "0"
             and transaction["signer_method"] == "eth_signTransaction")
    _require(parse_utc(transaction["request_expires_at"]) <= expiry)
    gas = value["gas"]
    _require(set(gas) == {"gas_limit", "max_fee_per_gas", "max_priority_fee_per_gas", "budget_raw"})
    _require(all(type(gas[x]) is int and gas[x] > 0 for x in ("gas_limit", "max_fee_per_gas")))
    _require(type(gas["max_priority_fee_per_gas"]) is int and 0 <= gas["max_priority_fee_per_gas"] <= gas["max_fee_per_gas"])
    _require(type(gas["budget_raw"]) is str and canonical_raw(gas["budget_raw"])
             and gas["gas_limit"] * gas["max_fee_per_gas"] <= int(gas["budget_raw"]))
    _require(value["finality"] == "finalized" and set(value["controls"]) == CONTROLS)
    for control in value["controls"].values():
        _require(type(control) is dict and set(control) == {"state", "evidence_class", "proof_sha256"})
        _require(control["state"] in ("ENFORCED", "UNKNOWN", "UNSUPPORTED", "UNSET"))
        _require(control["evidence_class"] in ("SYNTHETIC_FIXTURE", "DOCUMENTED", "SOURCE_INSPECTED", "LOCAL_TESTED", "PROVIDER_ACTUAL", "NOT_RUN"))
        _require(control["proof_sha256"] is None or _hash(control["proof_sha256"]))


@dataclass(frozen=True, init=False)
class OperatingRelease:
    _bytes: bytes = field(repr=False)

    def __init__(self, definition: Mapping[str, Any]) -> None:
        wire = None
        try:
            value = dict(definition)
            _validate(value)
            wire = canonical_bytes({"schema": SCHEMA, **value})
            if len(wire) > 65536:
                wire = None
        except Exception:
            pass
        if wire is None:
            raise ReleaseRefused("EXECUTION_RELEASE_INVALID")
        object.__setattr__(self, "_bytes", wire)

    def content(self) -> dict[str, Any]:
        """A fresh view; changing it cannot change authority or its hash."""
        return json.loads(self._bytes)


def release_sha256(release: OperatingRelease) -> str:
    return hashlib.sha256(release._bytes).hexdigest()


def check_release(release: OperatingRelease, *, expected_sha256: str, now: dt.datetime,
                  synthetic_approvals: Mapping[str, str] | None = None) -> str:
    """Admit only exact test-owned synthetic authority; ACTUAL has no override seam."""
    digest = release_sha256(release)
    content = release.content()
    if digest != expected_sha256:
        raise ReleaseRefused("EXECUTION_RELEASE_HASH_MISMATCH")
    if content["kind"] == "ACTUAL":
        if synthetic_approvals is not None or APPROVED_ACTUAL_RELEASES.get(content["release_id"]) != digest:
            raise ReleaseRefused("ACTUAL_EXECUTION_RELEASE_NOT_APPROVED")
    elif synthetic_approvals is None or synthetic_approvals.get(content["release_id"]) != digest:
        raise ReleaseRefused("SYNTHETIC_EXECUTION_RELEASE_NOT_APPROVED")
    if (not isinstance(now, dt.datetime) or now.tzinfo is None or now.utcoffset() != dt.timedelta(0)
            or now >= parse_utc(content["valid_until"])
            or now >= parse_utc(content["transaction"]["request_expires_at"])):
        raise ReleaseRefused("EXECUTION_RELEASE_EXPIRED")
    for control in content["controls"].values():
        if (control["state"] != "ENFORCED" or control["evidence_class"] != content["evidence_class"]
                or control["proof_sha256"] is None):
            raise ReleaseRefused("EXECUTION_CONTROL_UNQUALIFIED")
    return digest


_IDENTITY_FIELDS = frozenset({"owner_id", "agent_id", "wallet_id", "wallet_address", "network_id", "strategy_id",
    "publication_revision_id", "execution_revision_id", "market_binding_id", "content_sha256", "manifest_sha256",
    "consent_adoption_id", "consent_hash", "review_hash", "terms_hash"})


@dataclass(frozen=True, init=False)
class BoundRelease:
    """Immutable saved-identity and independent-proof binding, separately admitted from route authority."""

    release: OperatingRelease
    _bytes: bytes = field(repr=False)

    def __init__(self, release: OperatingRelease, identity: Mapping[str, str], *,
                 position_inventory_proof_sha256: str, market_proof_sha256: str,
                 finality_proof_sha256: str, exit_capacity_proof_sha256: str | None = None,
                 valuation_proof_sha256: str | None = None, cost_model_proof_sha256: str | None = None,
                 market_profile: Mapping[str, Any] | None = None) -> None:
        content = release.content()
        value = dict(identity)
        _require(set(value) == _IDENTITY_FIELDS and all(type(x) is str and 0 < len(x) <= 200 for x in value.values()))
        _require(value["wallet_id"] == content["wallet_id"] and value["wallet_address"] == content["wallet_address"]
                 and value["network_id"] == "monad:143")
        _require(all(_hash(value[x]) for x in ("content_sha256", "manifest_sha256")))
        _require(all(re.fullmatch(r"sha256:[0-9a-f]{64}", value[x]) for x in ("consent_hash", "review_hash", "terms_hash")))
        _require(all(_hash(x) for x in (position_inventory_proof_sha256, market_proof_sha256, finality_proof_sha256)))
        _require(all(x is None or _hash(x) for x in (exit_capacity_proof_sha256, valuation_proof_sha256, cost_model_proof_sha256)))
        profile = None if market_profile is None else dict(market_profile)
        if profile is not None:
            _require(set(profile) == {"source_id", "delivery_profile_sha256", "finality", "warmup_buckets", "max_collection_age_seconds"})
            _require(_text(profile["source_id"]) and _hash(profile["delivery_profile_sha256"]) and profile["finality"] == "finalized"
                     and type(profile["warmup_buckets"]) is int and 0 <= profile["warmup_buckets"] <= 10000
                     and type(profile["max_collection_age_seconds"]) is int
                     and 0 < profile["max_collection_age_seconds"] <= content["route"]["freshness"]["max_input_age_seconds"])
        wire = canonical_bytes({"schema": "edge-os.controlled-execution-binding/1", "identity": value,
            "release_sha256": release_sha256(release), "position_inventory_proof_sha256": position_inventory_proof_sha256,
            "market_proof_sha256": market_proof_sha256, "finality_proof_sha256": finality_proof_sha256,
            "exit_capacity_proof_sha256": exit_capacity_proof_sha256, "valuation_proof_sha256": valuation_proof_sha256,
            "cost_model_proof_sha256": cost_model_proof_sha256, "market_profile": profile})
        object.__setattr__(self, "release", release)
        object.__setattr__(self, "_bytes", wire)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self._bytes).hexdigest()

    def identity(self) -> dict[str, str]:
        return json.loads(self._bytes)["identity"]

    def proofs(self) -> dict[str, str | None]:
        return {key: value for key, value in json.loads(self._bytes).items() if key.endswith("_proof_sha256")}

    def market_profile(self) -> dict[str, Any] | None:
        return json.loads(self._bytes)["market_profile"]

    def admit(self, identity: Mapping[str, str], *, now: dt.datetime,
              synthetic_bindings: Mapping[str, str] | None = None) -> str:
        if dict(identity) != self.identity():
            raise ReleaseRefused("EXECUTION_BINDING_MISMATCH")
        content = self.release.content()
        digest = release_sha256(self.release)
        if content["kind"] == "ACTUAL":
            if synthetic_bindings is not None or APPROVED_ACTUAL_BINDINGS.get(self.sha256) != digest:
                raise ReleaseRefused("ACTUAL_EXECUTION_BINDING_NOT_APPROVED")
            approvals = None
        else:
            if synthetic_bindings is None or synthetic_bindings.get(self.sha256) != digest:
                raise ReleaseRefused("SYNTHETIC_EXECUTION_BINDING_NOT_APPROVED")
            approvals = {content["release_id"]: digest}
        check_release(self.release, expected_sha256=digest, now=now, synthetic_approvals=approvals)
        return self.sha256

    def qualify_original(self, original: Mapping[str, Any], *,
                         synthetic_bindings: Mapping[str, str] | None = None) -> str:
        """Verify saved authority at preparation time for read-only recovery after its signing expiry."""
        content = self.release.content()
        if (original.get("binding_sha256") != self.sha256
                or original.get("release_sha256") != release_sha256(self.release)
                or original.get("evidence_class") != content["evidence_class"]):
            raise ReleaseRefused("ORIGINAL_RELEASE_MISMATCH")
        self.admit({key: original.get(key) for key in self.identity()},
                   now=parse_utc(original["prepared_at"]), synthetic_bindings=synthetic_bindings)
        gas, route, unsigned = content["gas"], content["route"], original["unsigned"]
        if (original.get("chain_id") != 143 or unsigned.get("chain_id") != 143
                or unsigned.get("to", "").lower() != route["entrypoint_address"].lower()
                or unsigned.get("value") != 0
                or any(unsigned.get(key) != gas[key] for key in ("gas_limit", "max_fee_per_gas", "max_priority_fee_per_gas"))
                or original["sell"]["raw"] != route["approved_input_raw"]
                or any(original[leg].get(key) != route[asset].get(route_key)
                       for leg, asset in (("sell", "input_asset"), ("buy", "output_asset"))
                       for key, route_key in (("asset_id", "asset_id"), ("token", "token_address"), ("decimals", "decimals")))):
            raise ReleaseRefused("ORIGINAL_RELEASE_MISMATCH")
        from edge_os_api.kuru_flow.flow_calldata import decode_flow_call
        from edge_os_api.kuru_flow.types import candidate_identity

        call = decode_flow_call(data_hex=unsigned["data"], method=route["method"])
        if (call.selector != route["selector"] or call.program_hex != route["approved_program_hex"]
                or call.intent.amount_user_sells != route["approved_input_raw"]
                or call.intent.min_amount_user_buys != route["approved_min_output_raw"]
                or call.intent.token_user_sells.lower() != route["input_asset"]["token_address"].lower()
                or call.intent.token_user_buys.lower() != route["output_asset"]["token_address"].lower()
                or call.fees.model_dump(mode="json") != route["fees"]
                or (call.receiver is not None and call.receiver.lower() != route["recipient"].lower())):
            raise ReleaseRefused("ORIGINAL_ROUTE_MISMATCH")
        candidate = {"chain_id": 143, "to": unsigned["to"], "value_raw": "0", "data_hex": unsigned["data"],
                     "selector": call.selector, "method": call.method, "intent": call.intent.model_dump(mode="json"),
                     "fees": call.fees.model_dump(mode="json"), "program_hex": call.program_hex, "receiver": call.receiver}
        if candidate_identity(candidate) != original["candidate_hash"]:
            raise ReleaseRefused("ORIGINAL_CANDIDATE_MISMATCH")
        return content["evidence_class"]
