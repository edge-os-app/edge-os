"""Hermes application mount tests: the saved Research path over the accepted transport job, ACTUAL pinned Hermes in a
no-egress container, a migrated PostgreSQL database and separate API processes.

The pinned image is built once per session and removed at the end. No real provider, key or network is used.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "hermes_interpretation"))
sys.path.insert(0, str(REPO / "scripts" / "hermes_job_support"))
sys.path.insert(0, str(REPO / "apps" / "api" / "tests"))
sys.path.insert(0, str(REPO / "scripts" / "p03"))

from docker_turn_runner import PinnedHermesImage  # noqa: E402


def _api_fixtures() -> None:
    """Reuse the API test session (PostgreSQL container, signing key, tokens)."""
    spec = importlib.util.spec_from_file_location("edge_os_api_test_session", REPO / "apps" / "api" / "tests" / "conftest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("signer", "pg", "env", "migrated", "owner_a", "owner_b"):
        globals()[name] = getattr(module, name)


_api_fixtures()


@pytest.fixture(scope="session")
def run_id() -> str:
    return f"ham-{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="session")
def evidence_root(run_id: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    configured = os.environ.get("HERMES_APP_MOUNT_EVIDENCE_DIR")
    if not configured:
        return tmp_path_factory.mktemp(run_id)
    root = Path(configured) / run_id
    root.mkdir(parents=True, exist_ok=False)
    return root


@pytest.fixture(scope="session")
def pinned_hermes_image(run_id: str, evidence_root: Path):
    image = PinnedHermesImage(run_id, evidence_root / "image")
    tag = image.build()
    try:
        yield tag
    finally:
        cleanup = image.remove()
        (evidence_root / "image-cleanup.json").write_text(json.dumps(cleanup, indent=1) + "\n")
        assert cleanup["image_removed"] is True, cleanup
