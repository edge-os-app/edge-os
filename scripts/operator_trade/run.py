"""One operator-run WMON -> MOE trade on Monad chain 143.

Default mode is ``--dry-run``: read the chain, build the unsigned transactions, simulate them with
``eth_call`` and state overrides, print the plan and the worst-case USD cost. It loads no Privy
credential, constructs no signer and cannot send.

``--live`` requires the trade file SHA256, a new empty store directory and environment
credentials. It journals each step and fsyncs before signing and sending. An unknown outcome stops
the run and is never resent. If the swap fails after the approval, the revoke is attempted once.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from edge_os_api.research_history.http_clients.http_transport import StdlibHttpTransport

from scripts.operator_trade.credentials import (
    ENV_RPC_URL,
    LiveEnvironment,
    build_signer_factory,
    load_live_environment,
)
from scripts.operator_trade.dry_run import Simulation, simulate
from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.journal import Journal, write_result
from scripts.operator_trade.plan import TradePlan, plan_trade
from scripts.operator_trade.preflight import Preflight, read_allowance, read_balance, read_code_sha256, read_preflight
from scripts.operator_trade.rpc import OperatorRpc
from scripts.operator_trade.sequence import SequenceOutcome, execute
from scripts.operator_trade.trade_file import OperatorTrade, load_trade_file
from scripts.operator_trade.transactions import build_unsigned

SCHEMA = "edge-os.operator-trade/1"


@dataclass(frozen=True)
class PostChecks:
    allowance_zero: bool
    moe_increase_at_least_minimum: bool
    wmon_decrease_exactly_input: bool
    entrypoint_code_unchanged: bool

    def all_true(self) -> bool:
        return all(asdict(self).values())


def _plan_report(plan: TradePlan) -> dict[str, Any]:
    return {
        "input_raw": plan.input_raw,
        "expected_raw": plan.expected_raw,
        "minimum_raw": plan.minimum_raw,
        "slippage_bps": plan.slippage_bps,
        "base_fee_per_gas": plan.base_fee,
        "priority_fee_per_gas": plan.priority_fee,
        "max_fee_per_gas": plan.max_fee_per_gas,
        "total_gas": plan.total_gas,
        "gas_wei": plan.gas_wei,
        "worst_case_wei": plan.worst_case_wei,
        "worst_case_usd": str(plan.worst_case_usd),
        "usd_ceiling": str(plan.usd_ceiling),
    }


def _step_reports(trade: OperatorTrade, plan: TradePlan, preflight: Preflight,
                  simulations: tuple[Simulation, ...]) -> list[dict[str, Any]]:
    estimates = {item.step: item.gas_estimate for item in simulations}
    return [
        {
            "step": transaction.step,
            "nonce": transaction.nonce,
            "to": transaction.to,
            "value": transaction.value,
            "gas_limit": transaction.gas_limit,
            "gas_estimate": estimates.get(transaction.step),
            "selector": transaction.data[:10],
            "data_sha256": hashlib.sha256(bytes.fromhex(transaction.data[2:])).hexdigest(),
        }
        for transaction in build_unsigned(trade, plan, preflight)
    ]


def _gas_estimates(simulations: tuple[Simulation, ...]) -> dict[str, int | None]:
    return {item.step: item.gas_estimate for item in simulations}


def _balance_report(trade: OperatorTrade, plan: TradePlan, preflight: Preflight) -> dict[str, Any]:
    return {
        "start": trade.start,
        "active_steps": list(trade.steps),
        "gas_limit_total": preflight.active_gas_total,
        "max_fee_per_gas": plan.max_fee_per_gas,
        "native_balance_wei": preflight.native_balance,
        "required_native_wei": preflight.required_native_wei,
        "remaining_native_wei": preflight.remaining_native_wei,
    }


def run_post_checks(*, rpc: Any, trade: OperatorTrade, plan: TradePlan, preflight: Preflight,
                    outcome: SequenceOutcome) -> PostChecks:
    allowance = read_allowance(rpc, trade.wmon, trade.wallet_address, trade.entrypoint)
    moe = read_balance(rpc, trade.moe, trade.wallet_address)
    wmon = read_balance(rpc, trade.wmon, trade.wallet_address)
    code_unchanged = read_code_sha256(rpc, trade.entrypoint) == trade.code_sha256["entrypoint"]
    return PostChecks(
        allowance_zero=allowance == 0,
        moe_increase_at_least_minimum=(moe - preflight.moe_balance) >= plan.minimum_raw,
        wmon_decrease_exactly_input=(outcome.wmon_after_wrap is not None
                                    and outcome.wmon_after_wrap - wmon == plan.input_raw),
        entrypoint_code_unchanged=code_unchanged,
    )


def _rpc_from_environment(environ: dict[str, str], rpc: Any, transport: Any) -> Any:
    if rpc is not None:
        return rpc
    endpoint = environ.get(ENV_RPC_URL)
    if not endpoint:
        raise OperatorError("ENV_MISSING", ENV_RPC_URL)
    try:
        return OperatorRpc(transport=transport or StdlibHttpTransport(), endpoint=endpoint)
    except Exception as error:  # noqa: BLE001 - a bad endpoint value is never copied into the error
        raise OperatorError("RPC_ENDPOINT_INVALID") from error


def run_dry(*, trade: OperatorTrade, environ: dict[str, str], transport: Any, rpc: Any,
            print_fn: Any = print) -> int:
    rpc = _rpc_from_environment(environ, rpc, transport)
    preflight = read_preflight(rpc, trade)
    plan = plan_trade(trade, base_fee=preflight.base_fee, priority_fee=preflight.priority_fee,
                      reserve_wmon=preflight.reserve_wmon, reserve_moe=preflight.reserve_moe)
    simulations = simulate(rpc, trade, plan, preflight)
    warnings: list[str] = []
    if trade.start == "MON" and plan.input_above_signer_safe_integer:
        warnings.append(
            "wrap value is above 2**53-1: the installed PrivySignerClient refuses it until the lane-3 "
            "signer change; a live run stops before signing the wrap"
        )
    report = {
        "schema": SCHEMA,
        "mode": "DRY_RUN",
        "trade_file_sha256": trade.file_sha256,
        "chain_id": preflight.chain_id,
        "block": preflight.block_number,
        "wallet_address": trade.wallet_address,
        "start": trade.start,
        "plan": _plan_report(plan),
        "balance": _balance_report(trade, plan, preflight),
        "steps": _step_reports(trade, plan, preflight, simulations),
        "gas_estimates": _gas_estimates(simulations),
        "simulations": [asdict(item) for item in simulations],
        "credentials_read": False,
        "signed": 0,
        "sent": 0,
        "warnings": warnings,
    }
    print_fn(json.dumps(report, indent=1, sort_keys=True))
    return 0


def run_live(*, trade: OperatorTrade, confirm: str, store: str | None, environ: dict[str, str],
             transport: Any, rpc: Any, privy_transport: Any, signer_factory: Any = None,
             print_fn: Any = print) -> int:
    if not confirm:
        raise OperatorError("CONFIRM_REQUIRED")
    if confirm != trade.file_sha256:
        raise OperatorError("CONFIRM_MISMATCH")
    if not store:
        raise OperatorError("STORE_REQUIRED")
    Journal.check_store(Path(store))
    rpc = _rpc_from_environment(environ, rpc, transport)
    preflight = read_preflight(rpc, trade)
    plan = plan_trade(trade, base_fee=preflight.base_fee, priority_fee=preflight.priority_fee,
                      reserve_wmon=preflight.reserve_wmon, reserve_moe=preflight.reserve_moe)
    simulations = simulate(rpc, trade, plan, preflight)
    environment: LiveEnvironment = load_live_environment(environ)
    print_fn(json.dumps({"mode": "LIVE", "trade_file_sha256": trade.file_sha256, "start": trade.start,
                         "plan": _plan_report(plan), "balance": _balance_report(trade, plan, preflight),
                         "gas_estimates": _gas_estimates(simulations)}, indent=1, sort_keys=True))
    journal = Journal.create(Path(store))
    factory = signer_factory or build_signer_factory(environment, privy_transport or StdlibHttpTransport())
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        try:
            outcome = execute(rpc=rpc, trade=trade, plan=plan, preflight=preflight, signer_factory=factory,
                              journal=journal, now=time.monotonic, sleep=time.sleep)
        except Exception:  # noqa: BLE001 - keep the journal and still write the evidence record
            outcome = SequenceOutcome(ok=False, steps=(), failed_step=None, error_code="UNEXPECTED",
                                      wmon_after_wrap=None, revoke_attempted=False, revoke_ok=None,
                                      revoke_error=None)
    finally:
        journal.close()
    post: PostChecks | None = None
    post_error: str | None = None
    if outcome.ok:
        try:
            post = run_post_checks(rpc=rpc, trade=trade, plan=plan, preflight=preflight, outcome=outcome)
        except Exception as error:  # noqa: BLE001 - a failed read is evidence, not a crash
            post_error = getattr(error, "code", "POST_CHECK_READ_FAILED")
    result = {
        "schema": SCHEMA,
        "mode": "LIVE",
        "trade_file_sha256": trade.file_sha256,
        "started_utc": started,
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "chain_id": preflight.chain_id,
        "wallet_address": trade.wallet_address,
        "start": trade.start,
        "plan": _plan_report(plan),
        "balance": _balance_report(trade, plan, preflight),
        "gas_estimates": _gas_estimates(simulations),
        "outcome": "SUCCESS" if outcome.ok and post is not None and post.all_true() else "STOPPED",
        "failed_step": outcome.failed_step,
        "error_code": outcome.error_code,
        "revoke_attempted": outcome.revoke_attempted,
        "revoke_ok": outcome.revoke_ok,
        "revoke_error": outcome.revoke_error,
        "post_error": post_error,
        "steps": [asdict(step) for step in outcome.steps],
        "post_checks": asdict(post) if post is not None else None,
        "warnings": ([
            "wrap value is above 2**53-1: the installed PrivySignerClient refuses it until the lane-3 signer change"
        ] if trade.start == "MON" and plan.input_above_signer_safe_integer else []),
    }
    write_result(Path(store), result)
    print_fn(json.dumps({"mode": "LIVE", "outcome": result["outcome"],
                         "failed_step": result["failed_step"], "error_code": result["error_code"],
                         "steps": len(result["steps"])}, sort_keys=True))
    return 0 if result["outcome"] == "SUCCESS" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.operator_trade.run",
                                     description="One operator-run WMON -> MOE trade on Monad 143.")
    parser.add_argument("--trade-file", required=True, help="frozen operator trade file (JSON)")
    parser.add_argument("--dry-run", action="store_true", help="default: read, build, simulate, print")
    parser.add_argument("--live", action="store_true", help="sign and send the four transactions")
    parser.add_argument("--confirm", default="", help="SHA256 of the trade file (required with --live)")
    parser.add_argument("--store", default=None, help="new empty evidence directory (required with --live)")
    return parser


def main(argv: list[str] | None = None, *, environ: dict[str, str] | None = None, rpc: Any = None,
         transport: Any = None, privy_transport: Any = None, signer_factory: Any = None) -> int:
    args = _parser().parse_args(argv)
    environment = dict(os.environ if environ is None else environ)
    try:
        trade = load_trade_file(Path(args.trade_file))
        if args.live:
            if args.dry_run:
                raise OperatorError("LIVE_AND_DRY_CONFLICT")
            return run_live(trade=trade, confirm=args.confirm, store=args.store, environ=environment,
                            transport=transport, rpc=rpc, privy_transport=privy_transport,
                            signer_factory=signer_factory)
        if args.store:
            raise OperatorError("STORE_REQUIRES_LIVE")
        return run_dry(trade=trade, environ=environment, transport=transport, rpc=rpc)
    except OperatorError as error:
        print(json.dumps({"status": "REFUSED", "code": error.code, "detail": error.detail}, sort_keys=True))
        return 1
    except Exception:  # noqa: BLE001 - never echo unexpected provider or credential text
        print(json.dumps({"status": "FAILED", "code": "UNEXPECTED"}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
