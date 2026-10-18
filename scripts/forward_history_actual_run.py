"""Separately authorized actual recorder entry. No registry activation, replay or retry."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from edge_os_api.core.research.environment_credentials import EnvironmentCredentialSource
from edge_os_api.core.research.released_source_runtime import CredentialUnavailable
from scripts.forward_history_recorder import (
    MAX_INPUT_BYTES, AttemptExists, EvidenceWriteFailed, RecorderInputError, SystemClock, run_actual_attempt,
)
from scripts.history_payload_binding import PayloadError, read_bounded, strict_json


def main(argv: Sequence[str] | None = None) -> int:
    """Run one frozen input. The producer owns the sole transport and reads the existing selected-slot reader."""
    parser = argparse.ArgumentParser(description="Execute one separately authorized ACTUAL forward-history attempt.")
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        value = strict_json(read_bounded(args.input, MAX_INPUT_BYTES), "INPUT_NOT_STRICT_JSON")
        result = run_actual_attempt(value, clock=SystemClock(), credentials=EnvironmentCredentialSource().read)
    except (PayloadError, RecorderInputError) as error:
        print(json.dumps({"status": "REFUSED", "code": error.code}))
        return 2
    except (CredentialUnavailable, AttemptExists, EvidenceWriteFailed) as error:
        print(json.dumps({"status": "REFUSED", "code": type(error).__name__}))
        return 2
    except OSError as error:
        print(json.dumps({"status": "REFUSED", "code": "FILE_ERROR", "errno": error.errno}))
        return 2
    # Artifact paths are private and need not enter an operator log.
    print(json.dumps({key: item for key, item in result.items() if not key.endswith("_path")}))
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
