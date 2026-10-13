"""Hermes provider relay tests: admission, the job channel, the relay process and ACTUAL pinned Hermes behind the relay.

Unit tests need no Docker. The Docker tests build the pinned Hermes image once per session and remove it, run the relay
and the AUTHORED provider on an internal network of their own and remove them. No real provider, key or network is used:
the key is a synthetic sentinel and the provider answers from authored scripts.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for folder in ("scripts/hermes_interpretation", "scripts/hermes_job_support", "scripts/hermes_provider_relay",
               "apps/api/tests"):
    if str(REPO / folder) not in sys.path:
        sys.path.insert(0, str(REPO / folder))

import json  # noqa: E402
import os  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402

SENTINEL = "sk-test-RELAY-SENTINEL-4c1d9e7a2b6f8053"  # synthetic: no provider knows it


@pytest.fixture(scope="session")
def run_id() -> str:
    return f"hpr-{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="session")
def evidence_root(run_id: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    configured = os.environ.get("HERMES_RELAY_EVIDENCE_DIR")
    if not configured:
        return tmp_path_factory.mktemp(run_id)
    root = Path(configured) / run_id
    root.mkdir(parents=True, exist_ok=False)
    return root


@pytest.fixture(scope="session")
def pinned_hermes_image(run_id: str, evidence_root: Path):
    from docker_turn_runner import PinnedHermesImage

    image = PinnedHermesImage(run_id, evidence_root / "image")
    tag = image.build()
    try:
        yield tag
    finally:
        cleanup = image.remove()
        (evidence_root / "image-cleanup.json").write_text(json.dumps(cleanup, indent=1) + "\n")
        assert cleanup["image_removed"] is True, cleanup


@pytest.fixture(scope="session")
def synthetic_key(evidence_root: Path) -> Path:
    folder = evidence_root / "synthetic-key"
    folder.mkdir(mode=0o700)
    path = folder / "provider-key"
    path.write_text(SENTINEL, encoding="utf-8")
    path.chmod(0o400)
    return path


@pytest.fixture(scope="session")
def relay(pinned_hermes_image: str, run_id: str, evidence_root: Path, synthetic_key: Path):
    """One relay and AUTHORED provider for the session, serving one channel root: the shared job evidence folder."""
    from relay_harness import RELEASE
    from relay_supervisor import RelaySupervisor

    supervisor = RelaySupervisor(evidence_root / "relay", RELEASE, pinned_hermes_image, run_id, synthetic_key,
                                 {"jobs": evidence_root / "jobs"})
    try:
        supervisor.start()
        yield supervisor
    finally:
        (evidence_root / "relay-logs.txt").write_text(supervisor.logs(), encoding="utf-8")
        cleanup = supervisor.stop()
        (evidence_root / "relay-cleanup.json").write_text(json.dumps(cleanup, indent=1) + "\n")
        assert cleanup == {"containers_left": [], "networks_left": []}, cleanup


def _api_fixtures() -> None:
    """Reuse the API test session (PostgreSQL container, signing key, tokens) for the application tests."""
    import importlib.util

    if str(REPO / "scripts" / "p03") not in sys.path:
        sys.path.insert(0, str(REPO / "scripts" / "p03"))
    spec = importlib.util.spec_from_file_location("edge_os_api_test_session", REPO / "apps" / "api" / "tests" / "conftest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("signer", "pg", "env", "migrated", "owner_a", "owner_b"):
        globals()[name] = getattr(module, name)


_api_fixtures()
