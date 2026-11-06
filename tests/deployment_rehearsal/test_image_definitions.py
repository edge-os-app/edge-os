"""Image definitions and the exact build context they receive.

The context test sends the repository root through Docker's own .dockerignore handling into a scratch stage and
reads back the files, so it checks what a real build would see rather than re-implementing the ignore rules.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API_DOCKERFILE = REPO / "deploy" / "docker" / "api.Dockerfile"
WEB_DOCKERFILE = REPO / "apps" / "web" / "Dockerfile"
# Files the application opens through its own module paths at runtime (HOST_QUALIFICATION_RUNBOOK.md stage 1.4 and
# the parents[3]/parents[5] references in apps/api/src). Each must reach the API image.
RUNTIME_ASSETS = [
    "apps/api/alembic.ini", "apps/api/migrations/env.py", "apps/api/src/edge_os_api/main.py",
    "docs/contracts/p02/check_contract.py", "docs/contracts/p06/contract.json", "docs/qualification/p07/qualification.py",
    "docs/implementation/EFFECT_COMPARISON_PROFILE.md", "docs/implementation/SPOT_REPLAY_RUNTIME_PROFILE.md",
    "apps/api/tests/fixtures/effect_comparison/synthetic_effect_comparison_v1.json",
    "apps/api/tests/fixtures/spot_replay/runtime_wc01.json", "apps/api/tests/fixtures/research_history_recorded",
    "apps/api/tests/fixtures/research_history_native", "apps/api/tests/fixtures/nansen_research_authored",
    "scripts/hermes_interpretation/spend_ledger.py", "scripts/hermes_job_support/transport_turn_job.py",
    "scripts/history_payload_binding.py", "scripts/history_payload_binding_v2.py", "deploy/local/public_entry.py", "deploy/local/http_probe.py",
]
WEB_SOURCES = ["apps/web/package.json", "apps/web/package-lock.json", "apps/web/next.config.ts", "apps/web/tsconfig.json",
               "apps/web/app/layout.tsx", "apps/web/lib/api.ts", "apps/web/components", "apps/web/public"]
FORBIDDEN_IN_CONTEXT = re.compile(r"(^|/)(\.git|\.scratch|\.agents|\.claude|\.codex|\.venv|node_modules|__pycache__|"
                                  r"\.next[^/]*|\.pytest_cache)(/|$)|(^|/)\.env($|\.)")


def _from_lines(text: str) -> list[str]:
    return re.findall(r"^ARG (?:PYTHON|NODE)_IMAGE=(\S+)$", text, flags=re.M)


@pytest.mark.parametrize("dockerfile", [API_DOCKERFILE, WEB_DOCKERFILE], ids=["api", "web"])
def test_base_images_are_pinned_by_digest_and_runtime_user_is_not_root(dockerfile: Path) -> None:
    text = dockerfile.read_text()
    bases = _from_lines(text)
    assert bases and all(re.fullmatch(r"[a-z0-9.:-]+@sha256:[0-9a-f]{64}", base) for base in bases)
    stages = re.split(r"^FROM ", text, flags=re.M)
    final = stages[-1]
    users = re.findall(r"^USER (\S+)$", final, flags=re.M)
    assert users and users[-1] not in {"root", "0", "0:0"}
    assert re.search(r"^CMD \[", final, flags=re.M)


@pytest.mark.parametrize("dockerfile", [API_DOCKERFILE, WEB_DOCKERFILE], ids=["api", "web"])
def test_no_secret_or_runtime_configuration_is_baked_in(dockerfile: Path) -> None:
    text = dockerfile.read_text()
    declared = re.findall(r"^\s*(?:ARG|ENV)\s+([A-Z0-9_]+)", text, flags=re.M)
    declared += re.findall(r"^\s+([A-Z0-9_]+)=", text, flags=re.M)  # continuation lines of a multi-name ENV
    for name in declared:
        assert not re.search(r"SECRET|PASSWORD|TOKEN|PRIVATE|CREDENTIAL", name), name
        assert not name.startswith("EDGE_OS_") or name == "EDGE_OS_SOURCE_COMMIT", name
        assert not name.startswith("POSTGRES_"), name


def test_api_image_installs_only_the_frozen_lock_and_carries_every_runtime_asset() -> None:
    text = API_DOCKERFILE.read_text()
    assert "uv sync --frozen --no-dev --no-install-project" in text
    assert "UV_PYTHON_DOWNLOADS=never" in text
    copied = " ".join(re.findall(r"^COPY (?!--from)(.+) \S+$", text, flags=re.M))
    for asset in RUNTIME_ASSETS:
        assert (REPO / asset).exists(), asset
        assert any(asset == source or asset.startswith(source.rstrip("/") + "/") for source in copied.split()), asset


def test_web_image_takes_only_public_build_arguments_and_the_lock() -> None:
    text = WEB_DOCKERFILE.read_text()
    assert set(re.findall(r"^ARG ([A-Z0-9_]+)", text, flags=re.M)) == {
        "NODE_IMAGE", "NEXT_PUBLIC_API_BASE_URL", "NEXT_PUBLIC_PRIVY_APP_ID", "EDGE_OS_SOURCE_COMMIT"}
    assert "npm ci --ignore-scripts" in text and "npm install" not in text
    runtime = re.split(r"^FROM ", text, flags=re.M)[-1]
    assert "NEXT_PUBLIC_" not in runtime, "public values are inlined at build time, not passed to the server"


@pytest.fixture(scope="module")
def build_context(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("docker") is None:
        pytest.skip("Docker is required to read the exact build context")
    work = tmp_path_factory.mktemp("context")
    probe = work / "context.Dockerfile"
    probe.write_text("FROM scratch\nCOPY . /context/\n")
    output = work / "out"
    result = subprocess.run(["docker", "buildx", "build", "--no-cache", "--quiet", "-f", str(probe),
                             "--output", f"type=local,dest={output}", str(REPO)],
                            capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    return output / "context"


def test_build_context_holds_the_runtime_assets_and_web_sources(build_context: Path) -> None:
    for item in RUNTIME_ASSETS + WEB_SOURCES:
        assert (build_context / item).exists(), item


def test_build_context_excludes_local_state_private_material_and_unrelated_files(build_context: Path) -> None:
    files = sorted(str(path.relative_to(build_context)) for path in build_context.rglob("*") if path.is_file())
    assert files
    leaked = [name for name in files if FORBIDDEN_IN_CONTEXT.search(name)]
    assert leaked == []
    top = {name.split("/", 1)[0] for name in files}
    assert top == {"apps", "deploy", "docs", "scripts"}
    assert not any(name.startswith(("apps/api/tests/", "apps/web/tests/")) and not name.startswith("apps/api/tests/fixtures/")
                   for name in files)
    assert {name.split("/", 2)[1] for name in files if name.startswith("docs/")} <= {"contracts", "qualification", "implementation"}
    assert [name for name in files if name.startswith("deploy/")] == ["deploy/local/http_probe.py", "deploy/local/public_entry.py"]
    for name in files:
        data = (build_context / name).read_bytes()
        assert b"PRIVATE KEY-----" not in data, name
        assert b"EDGE_OS_PRIVY_APP_SECRET=" not in data, name
