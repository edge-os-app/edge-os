"""Load the frozen P07 and P02 modules and re-export the reused public seams.

The adapter owns no numerical or qualification logic. It loads the existing
qualification module (`docs/qualification/p07/qualification.py`) and the P02
contract checker (`docs/contracts/p02/check_contract.py`) by a repository-relative
path and re-exports the functions it composes. A missing or unreadable module is a
loud load failure, not a silent fallback.
"""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
P07_MODULE_PATH = REPO_ROOT / "docs" / "qualification" / "p07" / "qualification.py"
P02_CHECKER_PATH = REPO_ROOT / "docs" / "contracts" / "p02" / "check_contract.py"


class EngineUnavailable(RuntimeError):
    """The reused P07 or P02 module is missing or cannot be loaded."""


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EngineUnavailable(f"required module is absent: {path}")
    try:
        return runpy.run_path(str(path))
    except Exception as error:  # pragma: no cover - a broken dependency must fail loudly
        raise EngineUnavailable(f"cannot execute {path}: {error}") from error


_P07 = _load(P07_MODULE_PATH)
_P02 = _load(P02_CHECKER_PATH)


def module_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_bytes(value: Any) -> bytes:
    """Deterministic bytes for raw provider data that may hold a non-canonical value.

    A supplied response or record can carry a float or other value the P02 canonical
    encoder refuses. Such a value must reach the decoder as a refusal, not stop work.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str).encode("utf-8")


def raw_sha256(value: Any) -> str:
    return hashlib.sha256(raw_bytes(value)).hexdigest()


P07_MODULE_SHA256 = module_sha256(P07_MODULE_PATH)
P02_CHECKER_SHA256 = module_sha256(P02_CHECKER_PATH)

PROFILE_SCHEMA: str = _P07["PROFILE_SCHEMA"]
RESULT_SCHEMA: str = _P07["RESULT_SCHEMA"]
CLAIMS: tuple[str, ...] = tuple(_P07["CLAIMS"])

history_observations = _P07["history_observations"]
qualify = _P07["qualify"]
feasibility = _P07["feasibility"]
assemble_segments = _P07["assemble_segments"]
bucketize = _P07["bucketize"]
bucket_available_at = _P07["bucket_available_at"]
ingest = _P07["ingest"]
dataset_revision = _P07["dataset_revision"]
trade_identity = _P07["trade_identity"]
profile_sha256 = _P07["profile_sha256"]
canonical_sha256 = _P07["canonical_sha256"]
profile_problems = _P07["profile_problems"]
to_p02_binding = _P07["to_p02_binding"]
research_binding_view = _P07["research_binding_view"]
epoch = _P07["epoch"]
iso_utc = _P07["iso_utc"]

Unsupported = _P07["Unsupported"]
InvalidInput = _P07["InvalidInput"]
BindingNotEmittable = _P07["BindingNotEmittable"]
Trade = _P07["Trade"]

canonical_bytes = _P02["canonical_bytes"]


def engine_hashes() -> dict[str, str]:
    """The exact reused module bytes the adapter composes."""
    return {"p07_qualification": P07_MODULE_SHA256, "p02_checker": P02_CHECKER_SHA256}


def _self_check() -> None:  # pragma: no cover - exercised by import
    for name, value in (("history_observations", history_observations), ("qualify", qualify),
                        ("dataset_revision", dataset_revision), ("canonical_bytes", canonical_bytes)):
        if not callable(value):
            raise EngineUnavailable(f"reused seam is not callable: {name}")


_self_check()
