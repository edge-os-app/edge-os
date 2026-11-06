"""The P27 LOCAL recurring producer process: bounded passes of tick → reconcile → worker.

Run `python -m edge_os_api.execution.recurring_producer --once` for one pass, or `--interval S` for repeated
passes, optionally ending after `--max-passes N`. SIGTERM or SIGINT finishes the current pass and exits. Before
every pass the migration head is checked; schema drift exits 3 before any effect, as the bounded workers do.

`--clock-offset-minutes M` moves this process's clock for LOCAL verification only. It is refused unless the
execution mode is `fixture` and the environment is not production. It changes which slot is due, never a saved
decision time, and every observation, quote and receipt stays an authored fixture.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import signal
import sys
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from edge_os_api.core.database import SchemaMismatch, require_head
from edge_os_api.core.provider_ports import FIXTURE_MODE
from edge_os_api.execution.recurring_scheduler import RecurringOperation
from edge_os_api.execution.worker import ConnectedExecution

log = logging.getLogger("edge_os.recurring")
DRIFT_EXIT_CODE = 3
REFUSED_EXIT_CODE = 2
SKIPPED_EXIT_CODE = 4


class ClockOffsetRefused(RuntimeError):
    pass


def producer_clock(settings: Any, offset_minutes: float) -> Callable[[], dt.datetime]:
    """The producer's clock. A nonzero offset exists for LOCAL fixture verification only."""
    if offset_minutes and (settings.execution_mode != FIXTURE_MODE or settings.env == "production"):
        raise ClockOffsetRefused("a clock offset is accepted only in local fixture execution mode")
    offset = dt.timedelta(minutes=offset_minutes)
    return lambda: dt.datetime.now(dt.timezone.utc) + offset


def build_producer(factory: Any, settings: Any, clock: Callable[[], dt.datetime]) -> RecurringOperation:
    """Compose the producer over the accepted services, with one clock for the scheduler and its worker pass."""
    from edge_os_api.core.financial_services import build_financial_services

    services = build_financial_services(factory, settings, role="recurring")
    connected = ConnectedExecution(factory, services, services.ports, qualification=services.ports.mode, clock=clock)
    services.connected = connected
    return RecurringOperation(factory, services, connected, clock=clock)


def run_passes(engine: Engine, producer: RecurringOperation, *, once: bool, interval: float,
               max_passes: int | None, stopping: Callable[[], bool],
               sleep: Callable[[float], None] = time.sleep) -> int:
    """Run producer passes; returns 0, or 3 on schema drift. Every pass is bounded; nothing retries an effect."""
    passes = 0
    while True:
        try:
            require_head(engine)
        except SchemaMismatch as error:
            log.error("recurring producer stopped before any effect: schema drift (%s)", error)
            return DRIFT_EXIT_CODE
        except SQLAlchemyError as error:
            log.error("recurring producer skipped a pass: database unavailable (%s)", type(error).__name__)
            if once:
                return SKIPPED_EXIT_CODE  # a single requested pass that did not run is not a success
        else:
            try:
                results = producer.producer_pass()
                log.info("recurring producer pass %d: %d result(s)", passes + 1, len(results))
            except Exception as error:  # noqa: BLE001 - one failed pass must not stop the producer; state is durable
                log.error("recurring producer pass failed: %s", type(error).__name__)
        passes += 1
        if once or stopping() or (max_passes is not None and passes >= max_passes):
            return 0
        waited = 0.0
        while waited < interval:  # short slices, so a stop request ends the producer between passes promptly
            if stopping():
                return 0
            step = min(0.5, interval - waited)
            sleep(step)
            waited += step
        if stopping():
            return 0


def main(argv: list[str] | None = None) -> None:
    from edge_os_api.core.database import make_engine, make_session_factory
    from edge_os_api.core.settings import load_settings

    parser = argparse.ArgumentParser(description="Produce and advance recurring occurrences.")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    parser.add_argument("--interval", type=float, default=30.0, help="seconds between passes")
    parser.add_argument("--max-passes", type=int, default=None, help="exit after this many passes")
    parser.add_argument("--clock-offset-minutes", type=float, default=0.0,
                        help="LOCAL fixture verification only: shift this process's clock")
    args = parser.parse_args(argv)
    if args.interval <= 0 or (args.max_passes is not None and args.max_passes < 1):
        parser.error("--interval must be positive and --max-passes at least 1")
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    try:
        clock = producer_clock(settings, args.clock_offset_minutes)
    except ClockOffsetRefused as refused:
        log.error("recurring producer refused: %s", refused)
        sys.exit(REFUSED_EXIT_CODE)
    engine = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    producer = build_producer(make_session_factory(engine), settings, clock)
    stop = {"requested": False}

    def request_stop(*_: Any) -> None:
        stop["requested"] = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    code = run_passes(engine, producer, once=args.once, interval=args.interval, max_passes=args.max_passes,
                      stopping=lambda: stop["requested"])
    engine.dispose()
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()
