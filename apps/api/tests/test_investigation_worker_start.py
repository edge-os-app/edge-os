"""The research worker starts the way the host unit starts it and reaches the saved-data binding in one piece.

Each case is a real Python process with the real start line. A `sitecustomize` replaces only the database, settings
and loop edges, then runs `record_binding` where the loop would. No database, no network, no provider.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

import harness

WORKER_UNIT = harness.REPO / "deploy" / "host" / "edge-os-research-worker.service"
WORKER_MODULE = "edge_os_api.research.investigation_jobs"
REACHED = "binding reached, module imported by name"

START_EDGES = f'''
import importlib, sys, types, uuid
from edge_os_api.core import database, settings, worker_loop
from edge_os_api.core.research import released_runtime_bootstrap


class Reached(Exception):
    pass


class Session:
    def flush(self):
        raise Reached


def run_binding_once(*args, **kwargs):
    from edge_os_api.research import history_payload_binding
    zero = uuid.UUID(int=0)
    try:
        history_payload_binding.record_binding(Session(), owner_id=zero, job_id=zero, attempt_id=zero,
                                               dataset_id=zero, definition={{}})
    except Reached:
        importlib.import_module("{WORKER_MODULE}")
        print("{REACHED}")
    return 0


settings.load_settings = lambda: types.SimpleNamespace(database_url="unused", database_statement_timeout_ms=1,
                                                       env="test")
database.make_engine = lambda *args: "engine"
database.make_session_factory = lambda engine: "factory"
released_runtime_bootstrap.server_research_runtime = lambda loaded: None
worker_loop.run = run_binding_once
'''


def unit_start_arguments() -> list[str]:
    """The arguments after the interpreter in the repository unit's `ExecStart`."""
    lines = WORKER_UNIT.read_text(encoding="utf-8").splitlines()
    start = next(line for line in lines if line.startswith("ExecStart="))
    return shlex.split(start.removeprefix("ExecStart="))[1:]


@pytest.mark.parametrize("arguments", [
    pytest.param(unit_start_arguments(), id="repository-unit"),
    pytest.param(["-m", WORKER_MODULE, "--once"], id="python-m-once"),
    pytest.param(["-c", f"from {WORKER_MODULE} import main; main()", "--interval", "2"], id="host-drop-in"),
])
def test_a_started_worker_reaches_the_binding_and_can_import_itself_by_name(arguments: list[str],
                                                                            tmp_path: Path) -> None:
    (tmp_path / "sitecustomize.py").write_text(START_EDGES, encoding="utf-8")
    source = harness.API_DIR / "src"
    completed = subprocess.run(
        [sys.executable, *arguments], cwd=tmp_path, capture_output=True, text=True, timeout=120,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": f"{tmp_path}{os.pathsep}{source}",
             "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stderr[-1500:]
    assert REACHED in completed.stdout
