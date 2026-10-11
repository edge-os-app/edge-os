"""Wraps a Hermes turn runner with the request policy and the spend ledger. Support code, not wired into the app.

Order for one turn: check the turn against the policy, reserve the worst-case cost, run the wrapped runner, settle.
The wrapped runner is never called when the check or the reservation fails. After the run, only provable facts free
or fix a reservation: a counted single request with usable usage is charged exactly, and a run that admitted no
request is released. Anything else keeps the full reservation as liability and blocks the next attempt in its scope.
A failure to record a result never hides the result, and it never frees liability.

It implements the same `HermesTurnRunner` interface as the runner it wraps, so it fits where the application already
accepts a runner.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult, HermesTurnRunner
from edge_os_api.research.interpretation_attempts import Usage
from provider_guard import GuardPolicy
from spend_ledger import CapExceeded, ReservationExists, ScopeBlocked, SpendLedger

__all__ = ["GuardedTurnRunner", "INPUT_TOKEN_MARGIN"]

log = logging.getLogger(__name__)
# A token is at least one byte of text, so the request's bytes bound its input tokens. The margin covers the few
# special tokens that a provider's chat template adds. This is an assumption about tokenizers, not a proven ceiling.
INPUT_TOKEN_MARGIN = 64
COUNTED = ("RETURNED", "TRUNCATED")


def _refused(turn: HermesTurn, error_class: str) -> HermesTurnResult:
    return HermesTurnResult(status="PROVIDER_FAILED", text=None, usage=Usage(), request_count=0,
                            observed={"refusal": error_class}, error_class=error_class)


class GuardedTurnRunner:
    def __init__(self, delegate: HermesTurnRunner, ledger: SpendLedger, policy: GuardPolicy,
                 scope_for: Callable[[HermesTurn], str]) -> None:
        self._delegate, self._ledger, self._policy, self._scope_for = delegate, ledger, policy, scope_for

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        policy = self._policy
        logical = len(turn.system_prompt.encode("utf-8")) + len(turn.user_message.encode("utf-8"))
        if turn.model != policy.model or turn.max_output_tokens != policy.max_output_tokens or logical > policy.max_request_bytes:
            return _refused(turn, "RequestNotAdmitted")
        try:
            self._ledger.reserve(turn.attempt_id, scope=self._scope_for(turn),
                                 max_input_tokens=policy.max_request_bytes + INPUT_TOKEN_MARGIN,
                                 max_output_tokens=policy.max_output_tokens)
        except CapExceeded:
            return _refused(turn, "SpendCapReached")
        except ScopeBlocked:
            return _refused(turn, "SpendScopeBlocked")
        except ReservationExists:
            return _refused(turn, "ReservationExists")
        except Exception as error:  # noqa: BLE001 - without a recorded reservation no request may start
            log.error("spend reservation failed: %s", type(error).__name__)
            return _refused(turn, "SpendLedgerUnavailable")
        try:
            result = self._delegate.run_turn(turn)
        except BaseException as error:
            self._keep_liability(turn, type(error).__name__)
            raise
        return self._account(turn, result)

    def _keep_liability(self, turn: HermesTurn, reason: str) -> str:
        try:
            self._ledger.mark_unknown(turn.attempt_id, reason=reason)
        except Exception as error:  # noqa: BLE001 - the reservation stays RESERVED, which is also liability
            log.error("spend state not recorded: %s", type(error).__name__)
            return "SETTLEMENT_NOT_RECORDED"
        return "UNKNOWN"

    def _account(self, turn: HermesTurn, result: HermesTurnResult) -> HermesTurnResult:
        ledger, count = self._ledger, result.request_count
        try:
            if count == 0 and result.status != "TIMED_OUT":
                ledger.release_unsent(turn.attempt_id, reason=result.error_class or result.status)
                state, charge = "RELEASED", "0"
            elif count == 1 and result.status in COUNTED:
                usage = result.usage if result.usage.source == "PROVIDER_REPORTED" else Usage()
                settled = ledger.settle(turn.attempt_id, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
                state, charge = settled.state, str(settled.cost_usd.normalize())
            else:
                state, charge = self._keep_liability(turn, result.error_class or result.status), None
                if state == "UNKNOWN":
                    charge = str(ledger.liability_usd(turn.attempt_id).normalize())  # type: ignore[union-attr]
        except Exception as error:  # noqa: BLE001 - the result is real; the unrecorded settlement leaves liability in place
            log.error("spend settlement failed: %s", type(error).__name__)
            state, charge = "SETTLEMENT_NOT_RECORDED", None
        observed = {**result.observed, "spend_state": state}
        if charge is not None:
            observed["spend_charge_usd"] = charge
        return replace(result, observed=observed)
