"""Computes the identities that the Hermes transport job pins. Support code: it makes no request and reads no secret.

`python job_identities.py` prints them as JSON. `docs/qualification/hermes-job-support/JOB_IDENTITIES.json` is the
committed copy, and a test fails when the two differ.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ACCEPTED = HERE.parent / "hermes_interpretation"
BASE_COMMIT = "c9a6ac83dbb686dd744ca093c05f6932639df54c"
HERMES_COMMIT = "54bc5e509c985f37265c3d416bd2c64b10fc77ba"
HERMES_UV_LOCK_SHA256 = "de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01"
JOB_FILES = ["provider_transport.py", "authored_transport.py", "transport_turn_job.py", "transport_turn_runner.py",
             "job_identities.py"]
ACCEPTED_FILES = ["Dockerfile", "hermes_turn_job.py", "docker_turn_runner.py", "guarded_docker_runner.py",
                  "provider_guard.py", "guarded_turn_runner.py", "spend_ledger.py"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute() -> dict[str, Any]:
    return {
        "label": "LOCAL_AUTHORED_TRANSPORT_ACTUAL_NOT_RUN",
        "base_commit": BASE_COMMIT,
        "hermes_commit": HERMES_COMMIT,
        "hermes_uv_lock_sha256": HERMES_UV_LOCK_SHA256,
        "job_files_sha256": {name: sha256(HERE / name) for name in JOB_FILES},
        "accepted_files_sha256": {name: sha256(ACCEPTED / name) for name in ACCEPTED_FILES},
    }


if __name__ == "__main__":
    print(json.dumps(compute(), indent=1, sort_keys=True))
