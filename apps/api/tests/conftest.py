"""Test session: one run-labelled PostgreSQL container, a test signing key and real application instances."""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import harness
from tokens import OWNER_A, OWNER_B, TestSigner

from edge_os_api.main import create_app
from edge_os_api.settings import load_settings

EVIDENCE = Path(os.environ.get("P03_EVIDENCE_DIR", harness.REPO / ".scratch" / "p03" / "evidence" / "pytest"))


@pytest.fixture(scope="session")
def signer() -> TestSigner:
    return TestSigner()


@pytest.fixture(scope="session")
def pg():
    before = harness.orphan_report()
    instance = harness.Postgres(harness.new_run_id())
    try:
        instance.start()  # inside the try: a start that fails after creating the container must still be cleaned up
        yield instance
    finally:
        instance.stop_and_remove()
        assert instance.leftovers() == [], "cleanup left resources behind"
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "orphans-before.json").write_text(str(before))


@pytest.fixture(scope="session")
def env(pg, signer):
    return harness.api_env(database_url=pg.url, public_pem=signer.public_pem, previous_pem=None,
                           cors=["http://127.0.0.1:3999"])


@pytest.fixture(scope="session")
def migrated(pg, env):
    result = harness.migrate(env)
    assert result.returncode == 0, result.stderr
    return pg


@pytest.fixture(scope="session")
def settings(env, migrated):
    return load_settings(env)


@pytest.fixture(scope="session")
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def owner_a(signer) -> dict[str, str]:
    return {"Authorization": f"Bearer {signer.token(f'{OWNER_A}-{uuid.uuid4().hex[:8]}')}"}


@pytest.fixture
def owner_b(signer) -> dict[str, str]:
    return {"Authorization": f"Bearer {signer.token(f'{OWNER_B}-{uuid.uuid4().hex[:8]}')}"}


class LiveApi:
    def __init__(self, env: dict[str, str], log_dir: Path):
        self.env, self.log_dir, self.process, self.port = env, log_dir, None, 0

    def start(self) -> "LiveApi":
        self.port = harness.free_port()
        self.process = harness.start_api(self.env, self.port, self.log_dir)
        harness.wait_http(f"{self.url}/readyz")
        return self

    def stop(self) -> None:
        if self.process:
            self.process.stop()
            self.process = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture(scope="session")
def live_api(env, migrated, tmp_path_factory):
    api = LiveApi(env, tmp_path_factory.mktemp("live-api")).start()
    try:
        yield api
    finally:
        api.stop()


def run_threads(count: int, target) -> list:
    barrier, results = threading.Barrier(count), [None] * count

    def worker(index: int) -> None:
        barrier.wait()
        results[index] = target(index)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results
