"""Complete the authored in-app WMON -> MOE release and its saved-identity binding. Pure; no I/O but file reads.

The authored file (`docs/qualification/inapp-trade/release.authored.json`) fixes every bindable fact of the one
action. Values that only a recorded live read, a later lane or the builder's sign-in can supply are `{"$fill": name}`
markers. The controller supplies them in one frozen fill file; this module refuses a missing, extra or malformed
fill, a gas limit below `ceil(estimate * 1.2)`, and a worst case above the USD ceiling, then builds the
`OperatingRelease`. Registration stays a reviewed one-line change in `operating_release.py`; nothing here adds
authority. See `docs/qualification/inapp-trade/INAPP_TRADE_RELEASE.md`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from edge_os_api.execution.connected_identity import adopted_consent, resolve_agent, saved_release_identity
from edge_os_api.execution.direct_route_quote_client import PROGRAM_FEE_SCALE
from edge_os_api.execution.operating_release import (BoundRelease, OperatingRelease, ReleaseRefused, release_sha256,
                                                     validate_limits)
from edge_os_api.execution.original_transaction import wallet_address

AUTHORED_SCHEMA = "edge-os.inapp-trade-authoring/1"
FILL_FIELDS = frozenset({"quote_endpoint", "broadcast_endpoint", "observer_endpoint", "valid_until",
                         "mandate_expires_at", "abi_sha256", "mutable_router_proof_sha256", "reserves", "gas_estimates"})
BINDING_FILL_FIELDS = frozenset({"identity", "position_inventory_proof_sha256", "market_proof_sha256",
    "finality_proof_sha256", "exit_capacity_proof_sha256", "valuation_proof_sha256", "cost_model_proof_sha256",
    "market_profile"})
GAS_STEPS = ("wrap", "approve", "swap", "revoke")
MAX_USD_CEILING = Decimal("2.00")
WEI_PER_MON = 10**18
GAS_MARGIN = "1.2"  # the rule below is ceil(estimate * 6 / 5)
_RAW = re.compile(r"0|[1-9][0-9]{0,77}")


def _raw(value: Any) -> bool:
    return type(value) is str and _RAW.fullmatch(value) is not None


def required_gas_limit(estimate: int) -> int:
    """`ceil(estimate * 1.2)` in exact integer arithmetic."""
    return (estimate * 6 + 4) // 5


def check_gas_limits(limits: Mapping[str, int], estimates: Mapping[str, int], steps: Sequence[str]) -> None:
    for step in steps:
        if limits[step] < required_gas_limit(estimates[step]):
            raise ReleaseRefused("GAS_LIMIT_TOO_LOW")


def minimum_output_raw(*, input_raw: int, reserve_in: int, reserve_out: int, fee_ppm: int, slippage_bps: int) -> int:
    """The direct V2 program's expected output floored by the release slippage, as the quote client checks it."""
    kept = PROGRAM_FEE_SCALE - fee_ppm
    output = input_raw * kept * reserve_out // (reserve_in * PROGRAM_FEE_SCALE + input_raw * kept)
    return output * (10000 - slippage_bps) // 10000


def _decimal(value: Any) -> Decimal:
    try:
        number = Decimal(value) if type(value) is str else None
    except InvalidOperation:
        number = None
    if number is None or not number.is_finite() or number <= 0:
        raise ReleaseRefused("INAPP_AUTHORED_INVALID")
    return number


def _facts(authored: Mapping[str, Any]) -> dict[str, Any]:
    if type(authored) is not dict or set(authored) != {"schema", "facts", "release"} \
            or authored["schema"] != AUTHORED_SCHEMA or type(authored["release"]) is not dict:
        raise ReleaseRefused("INAPP_AUTHORED_INVALID")
    facts = authored["facts"]
    limits = facts.get("gas_limits") if type(facts) is dict else None
    release = authored["release"]
    gas = release.get("gas")
    if (type(facts) is not dict or not all(type(release.get(part)) is dict for part in ("gas", "route", "quote"))
            or facts.get("gas_margin") != GAS_MARGIN
            or type(limits) is not dict or set(limits) != set(GAS_STEPS)
            or not all(type(x) is int and x > 0 for x in limits.values())
            or facts.get("start") != "WMON" or facts.get("active_steps") != ["approve", "swap", "revoke"]
            or type(facts.get("recorded_swap_estimate")) is not int or facts["recorded_swap_estimate"] <= 0
            or gas.get("gas_limit") != limits["swap"]
            or _decimal(facts.get("usd_ceiling")) > MAX_USD_CEILING):
        raise ReleaseRefused("INAPP_AUTHORED_INVALID")
    # The release names the same steps, each with its own single signer request and broadcast, and its gas budget
    # covers every one of them at the fixed maximum fee.
    try:
        validate_limits(release.get("limits"))
    except ReleaseRefused:
        raise ReleaseRefused("INAPP_AUTHORED_INVALID") from None
    budget, max_fee = gas.get("budget_raw"), gas.get("max_fee_per_gas")
    if ([step["step"] for step in release["limits"].get("steps") or []] != facts["active_steps"]
            or not _raw(budget) or type(max_fee) is not int or max_fee <= 0
            or int(budget) < sum(limits[step] for step in facts["active_steps"]) * max_fee):
        raise ReleaseRefused("INAPP_AUTHORED_INVALID")
    _decimal(facts.get("mon_usd_price"))
    return facts


def worst_case_usd(authored: Mapping[str, Any]) -> Decimal:
    """Input value plus every step's full gas limit at the fixed maximum fee, at the documented MON price.

    Monad charges the full gas limit. All four step limits count, including the wrap a WMON start does not run.
    """
    facts = _facts(authored)
    release = authored["release"]
    max_fee, input_raw = release["gas"].get("max_fee_per_gas"), release["route"].get("approved_input_raw")
    if type(max_fee) is not int or max_fee <= 0 or type(input_raw) is not str or not _raw(input_raw):
        raise ReleaseRefused("INAPP_AUTHORED_INVALID")
    worst_wei = int(input_raw) + sum(facts["gas_limits"].values()) * max_fee
    return Decimal(worst_wei) * _decimal(facts["mon_usd_price"]) / Decimal(WEI_PER_MON)


def _substitute(value: Any, fills: Mapping[str, Any], used: set[str]) -> Any:
    if type(value) is dict:
        if set(value) == {"$fill"}:
            name = value["$fill"]
            if type(name) is not str or name not in fills:
                raise ReleaseRefused("INAPP_FILL_INVALID")
            used.add(name)
            return fills[name]
        return {key: _substitute(item, fills, used) for key, item in value.items()}
    if type(value) is list:
        return [_substitute(item, fills, used) for item in value]
    return value


def _positive_raw(value: Any) -> int:
    if not _raw(value) or int(value) <= 0:
        raise ReleaseRefused("INAPP_FILL_INVALID")
    return int(value)


def complete_release(authored: Mapping[str, Any], fill: Mapping[str, Any]) -> OperatingRelease:
    """The exact release for one frozen fill. Every refusal happens before any read, signature or send."""
    facts = _facts(authored)
    if type(fill) is not dict or set(fill) != FILL_FIELDS:
        raise ReleaseRefused("INAPP_FILL_INVALID")
    reserves, estimates = fill["reserves"], fill["gas_estimates"]
    steps = facts["active_steps"]
    if (type(reserves) is not dict or set(reserves) != {"block_number", "reserve_wmon", "reserve_moe"}
            or type(reserves["block_number"]) is not int or reserves["block_number"] <= 0
            or type(estimates) is not dict or set(estimates) != set(steps)
            or not all(type(x) is int and x > 0 for x in estimates.values())):
        raise ReleaseRefused("INAPP_FILL_INVALID")
    reserve_wmon, reserve_moe = _positive_raw(reserves["reserve_wmon"]), _positive_raw(reserves["reserve_moe"])
    check_gas_limits(facts["gas_limits"], estimates, steps)
    check_gas_limits(facts["gas_limits"], {"swap": facts["recorded_swap_estimate"]}, ["swap"])
    if worst_case_usd(authored) > _decimal(facts["usd_ceiling"]):
        raise ReleaseRefused("USD_CEILING_EXCEEDED")
    release = authored["release"]
    route, quote = release.get("route"), release.get("quote")
    try:
        input_raw = int(route["approved_input_raw"])
        direction, fee_ppm, slippage = quote["direction"], quote["program_fee_ppm"], quote["slippage_bps"]
        valid = (direction == 0 and type(fee_ppm) is int and 0 < fee_ppm < PROGRAM_FEE_SCALE
                 and type(slippage) is int and 1 <= slippage <= 10000)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ReleaseRefused("INAPP_AUTHORED_INVALID")
    minimum = minimum_output_raw(input_raw=input_raw, reserve_in=reserve_wmon, reserve_out=reserve_moe,
                                 fee_ppm=fee_ppm, slippage_bps=slippage)
    if minimum <= 0:
        raise ReleaseRefused("MINIMUM_OUTPUT_ZERO")
    fills = {key: fill[key] for key in FILL_FIELDS - {"reserves", "gas_estimates"}}
    fills["approved_min_output_raw"] = str(minimum)
    if not all(type(fill[key]) is str and re.fullmatch(r"[0-9a-f]{64}", fill[key])
               for key in ("abi_sha256", "mutable_router_proof_sha256")):
        raise ReleaseRefused("INAPP_FILL_INVALID")
    used: set[str] = set()
    definition = _substitute(release, fills, used)
    if used != set(fills):
        raise ReleaseRefused("INAPP_AUTHORED_INVALID")
    return OperatingRelease(definition)


def unqualified_controls(release: OperatingRelease) -> list[str]:
    """Controls that keep `check_release` refusing: not ENFORCED with the release's evidence class and a proof."""
    content = release.content()
    return sorted(name for name, control in content["controls"].items()
                  if control["state"] != "ENFORCED" or control["evidence_class"] != content["evidence_class"]
                  or control["proof_sha256"] is None)


def bind_release(release: OperatingRelease, binding_fill: Mapping[str, Any]) -> BoundRelease:
    """The saved-identity binding. Its identity must be read from the builder's records, never authored."""
    if type(binding_fill) is not dict or set(binding_fill) != BINDING_FILL_FIELDS \
            or type(binding_fill["identity"]) is not dict:
        raise ReleaseRefused("INAPP_BINDING_FILL_INVALID")
    try:
        return BoundRelease(release, binding_fill["identity"], **{
            key: binding_fill[key] for key in BINDING_FILL_FIELDS - {"identity"}})
    except ReleaseRefused:
        raise
    except (KeyError, TypeError, ValueError):
        raise ReleaseRefused("INAPP_BINDING_FILL_INVALID") from None


def saved_identity_for_release(session: Any, owner_id: uuid.UUID, agent_id: str,
                               release: OperatingRelease) -> dict[str, str]:
    """The binding identity of the builder's confirmed agent and adopted consent, exactly as the worker derives it."""
    agent = resolve_agent(session, owner_id, agent_id)
    consent = adopted_consent(session, agent) if agent is not None else None
    address = wallet_address(session, owner_id, agent_id, agent.wallet_id) if consent is not None else None
    if address is None:
        raise ReleaseRefused("SAVED_IDENTITY_UNAVAILABLE")
    identity = saved_release_identity(agent, consent, address)
    content = release.content()
    if (identity.get("wallet_id"), identity.get("wallet_address")) != (content["wallet_id"], content["wallet_address"]):
        raise ReleaseRefused("SAVED_IDENTITY_WALLET_MISMATCH")
    return identity


def registry_lines(release: OperatingRelease, binding: BoundRelease) -> list[str]:
    """The exact replacement lines for `operating_release.py`; adding them needs the builder's recorded approval."""
    digest = release_sha256(release)
    return [
        f'APPROVED_ACTUAL_RELEASES: Mapping[str, str] = MappingProxyType({{"{release.content()["release_id"]}": "{digest}"}})',
        f'APPROVED_ACTUAL_BINDINGS: Mapping[str, str] = MappingProxyType({{"{binding.sha256}": "{digest}"}})',
    ]


def _read(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m edge_os_api.execution.inapp_trade_release")
    parser.add_argument("--authored", required=True)
    parser.add_argument("--fill", required=True)
    parser.add_argument("--binding-fill")
    options = parser.parse_args(argv)
    try:
        release = complete_release(_read(options.authored), _read(options.fill))
        result: dict[str, Any] = {"status": "COMPLETED", "release_id": release.content()["release_id"],
                                  "release_sha256": release_sha256(release), "release": release.content(),
                                  "unqualified_controls": unqualified_controls(release)}
        if options.binding_fill is not None:
            binding = bind_release(release, _read(options.binding_fill))
            result.update(binding_sha256=binding.sha256, registry_lines=registry_lines(release, binding))
    except ReleaseRefused as error:
        print(json.dumps({"status": "REFUSED", "code": str(error)}))
        return 2
    except (OSError, ValueError):
        print(json.dumps({"status": "REFUSED", "code": "INAPP_FILE_UNREADABLE"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
