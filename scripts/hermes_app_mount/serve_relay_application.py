"""Start the API on loopback with the approved Hermes relay application release (`open_hermes_application`).

Run it from `apps/api` with the API's Python, the usual EDGE_OS_* environment and EDGE_OS_INTERPRETER=hermes_local
(refused in production). `--handoff-path` and `--handoff-sha256` are the line the relay operator printed at start;
`--run-id` is this API process's stable id (a restart reuses it to recover its own dead turns). The relay operator
started the relay and owns its shutdown: this process never stops it, and on exit closes only its own database engine.

With no approved release (the default: both registries are empty) it refuses and exits 2 before it reads the handoff
or opens a database, Docker or network connection.
See `docs/qualification/hermes-application-launcher/LOCAL_VERIFICATION.md`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.research.hermes_relay_composition import open_hermes_application
from edge_os_api.research.hermes_transport_mount import MountRefused

HOST = "127.0.0.1"
REFUSED = 2
NO_RELEASE = "no approved Hermes relay application release: nothing to serve"


def port(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be a whole number from 1 to 65535") from None
    if not 1 <= number <= 65_535:
        raise argparse.ArgumentTypeError("port must be a whole number from 1 to 65535")
    return number


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--handoff-path", type=Path, required=True)
    parser.add_argument("--handoff-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--port", type=port, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings()
    try:
        opened = open_hermes_application(settings, handoff_path=args.handoff_path, handoff_sha256=args.handoff_sha256,
                                         run_id=args.run_id)
    except MountRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return REFUSED
    if opened is None:
        print(f"refused: {NO_RELEASE}", file=sys.stderr)
        return REFUSED
    try:
        app = create_app(settings, hermes_runner=opened.runner, hermes_config=opened.config)
        print(json.dumps({"serving": opened.release.actual.release.release_id, "host": HOST, "port": args.port,
                          "pid": os.getpid(), "startup_recovered": len(opened.startup_recovery)}), flush=True)
        uvicorn.run(app, host=HOST, port=args.port, log_level="warning")
    finally:
        opened.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
