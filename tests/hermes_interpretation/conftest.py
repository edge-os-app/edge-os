"""One pinned-Hermes container image per test session, removed at the end. No egress, no real provider."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "hermes_interpretation"))
sys.path.insert(0, str(REPO / "apps" / "api" / "tests"))  # the append-only MemoryAttemptStore used by the unit tests

from docker_turn_runner import PinnedHermesImage  # noqa: E402


def _api_fixtures() -> None:
    """Reuse the API test session (PostgreSQL container, signing key, tokens) for the HTTP-level pinned-Hermes tests."""
    import importlib.util
    sys.path.insert(0, str(REPO / "scripts" / "p03"))
    spec = importlib.util.spec_from_file_location("edge_os_api_test_session", REPO / "apps" / "api" / "tests" / "conftest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("signer", "pg", "env", "migrated", "owner_a", "owner_b"):
        globals()[name] = getattr(module, name)


_api_fixtures()


@pytest.fixture(scope="session")
def run_id() -> str:
    return f"p05-{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session")
def evidence_root(run_id: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    configured = os.environ.get("P05_EVIDENCE_DIR")
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
        (evidence_root / "image-cleanup.json").write_text(__import__("json").dumps(cleanup, indent=1) + "\n")
        assert cleanup["image_removed"] is True, cleanup
