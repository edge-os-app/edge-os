"""The bounded loop both background workers share.

Before every pass the loop checks that the database schema is the code's migration head. On drift it stops the
process before any further effect (exit code 3); saved jobs, attempts and original actions stay as they are, and a
restart after migration recovers them through the workers' own reconciliation. A database that cannot be reached
skips the pass, so nothing runs against an unknown state. One failed pass never stops the loop.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from edge_os_api.core.database import SchemaMismatch, require_head

DRIFT_EXIT_CODE = 3


def run(name: str, engine: Engine, step: Callable[[], list[Any]], *, once: bool, interval: float,
        log: logging.Logger, sleep: Callable[[float], None] = time.sleep) -> int:
    """Run passes until `once` ends it; returns the exit code (0, or 3 on schema drift)."""
    while True:
        try:
            require_head(engine)
        except SchemaMismatch as error:
            log.error("%s stopped before any effect: schema drift (%s)", name, error)
            return DRIFT_EXIT_CODE
        except SQLAlchemyError as error:
            log.error("%s skipped a pass: database unavailable (%s)", name, type(error).__name__)
        else:
            try:
                advanced = step()
                if advanced:
                    log.info("%s advanced %d job(s)", name, len(advanced))
            except Exception as error:  # noqa: BLE001 - one failed pass must not stop the worker; state is durable
                log.error("%s pass failed: %s", name, type(error).__name__)
        if once:
            return 0
        sleep(interval)


def exit_with(code: int) -> None:
    if code:
        sys.exit(code)
