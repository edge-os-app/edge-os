"""Run the API with the ACTUAL pinned Hermes against a LOCAL FAKE provider. Test support only.

Each model turn runs in a no-network container and the provider answers from an authored script queue. No real
provider, key or account is involved, and the setting that selects this interpreter is refused in production.
Run it with the API's Python: the application settings come from the usual EDGE_OS_* environment, plus
EDGE_OS_INTERPRETER=hermes_local.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from authored_cases import ScriptQueue
from docker_turn_runner import DockerHermesTurnRunner
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app


def build_app(*, image: str, run_id: str, evidence_dir: Path, script_file: Path):
    settings = load_settings()
    runner = DockerHermesTurnRunner(image=image, run_id=run_id, evidence_dir=evidence_dir,
                                    script_for=ScriptQueue(script_file), forbidden=[])
    return create_app(settings, hermes_runner=runner)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--image", required=True, help="tag of an image built from the pinned Hermes source")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--script-file", type=Path, required=True)
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    app = build_app(image=args.image, run_id=args.run_id, evidence_dir=args.evidence_dir, script_file=args.script_file)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
