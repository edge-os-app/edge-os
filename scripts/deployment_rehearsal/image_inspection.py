"""Read-only checks of the built images: identity, runtime user, runtime assets, and a scan for run secrets.

The scan exports each image's filesystem from a never-started container and searches every regular file for the
run's generated values (database passwords, the synthetic key material, minted tokens) and for private-key blocks.
Private-key blocks are searched in the application tree (/app, outside node_modules). The web bundle (.next) is checked for the test-auth fixture label, as in the mapped verifier's bundle scan.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from local_stack import sh, text

PEM_PRIVATE = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----[\\nA-Za-z0-9+/=\s]{40,}")
# The API image must open every file the application reads through its module paths (see test_image_definitions).
ASSET_CHECK = """
import importlib, json, pathlib
modules = ["edge_os_api.main", "edge_os_api.records.contract_adapter", "edge_os_api.strategies.compiler",
           "edge_os_api.research_history.qualification_engine", "edge_os_api.research.comparison_runs",
           "edge_os_api.replay.saved_runs", "edge_os_api.research.history_dataset",
           "edge_os_api.core.research.provider_composition", "edge_os_api.research.provider_spend_ledger",
           "edge_os_api.research.hermes_transport_mount"]
loaded = {name: importlib.import_module(name) for name in modules}
paths = {
  "p02_contract_dir": loaded["edge_os_api.records.contract_adapter"].CONTRACT_DIR,
  "p06_contract": loaded["edge_os_api.strategies.compiler"].CONTRACT_PATH,
  "p07_module": loaded["edge_os_api.research_history.qualification_engine"].P07_MODULE_PATH,
  "p02_checker": loaded["edge_os_api.research_history.qualification_engine"].P02_CHECKER_PATH,
  "effect_profile": loaded["edge_os_api.research.comparison_runs"].PROFILE_PATH,
  "effect_fixture": loaded["edge_os_api.research.comparison_runs"].FIXTURE_PATH,
  "replay_profile": loaded["edge_os_api.replay.saved_runs"].PROFILE_PATH,
  "replay_fixture": loaded["edge_os_api.replay.saved_runs"].FIXTURE_PATH,
  "recorded_bundle": loaded["edge_os_api.research.history_dataset"].BUNDLE_PATH,
  "native_bundle": loaded["edge_os_api.research.history_dataset"].NATIVE_BUNDLE_PATH,
  "nansen_fixture": loaded["edge_os_api.core.research.provider_composition"].NANSEN_FIXTURE_PATH,
  "spend_support": loaded["edge_os_api.research.provider_spend_ledger"].SUPPORT,
  "job_support": loaded["edge_os_api.research.hermes_transport_mount"].JOB_SUPPORT,
}
print(json.dumps({key: [str(value), pathlib.Path(value).exists()] for key, value in paths.items()}))
"""


def image_identity(tag: str) -> dict[str, Any]:
    info = json.loads(text(sh(["docker", "image", "inspect", tag])))[0]
    config = info.get("Config") or {}
    return {"tag": tag, "id": info["Id"], "created": info.get("Created"), "size": info.get("Size"),
            "user": config.get("User"), "labels": config.get("Labels") or {}, "architecture": info.get("Architecture"),
            "env_names": sorted(item.split("=", 1)[0] for item in config.get("Env") or [])}


def runtime_user(tag: str) -> str:
    return text(sh(["docker", "run", "--rm", "--network", "none", "--entrypoint", "id", tag, "-u"], timeout=60))


def api_assets(tag: str) -> dict[str, Any]:
    result = sh(["docker", "run", "--rm", "--network", "none", "--read-only", tag, "python", "-c", ASSET_CHECK],
                check=False, timeout=120)
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or b"").decode("utf-8", "replace")[-600:]}
    paths = json.loads(text(result))
    return {"ok": all(found for _, found in paths.values()), "paths": paths}


def scan_filesystem(tag: str, needles: dict[str, str]) -> dict[str, Any]:
    """Export a never-started container of `tag` and search it. Returns file paths per finding, never the values."""
    created = sh(["docker", "create", "--network", "none", tag], timeout=60)
    container = text(created)
    findings: dict[str, list[str]] = {name: [] for name in needles}
    findings.update({"private_key_block": [], "fixture_label_in_web_bundle": []})
    encoded = {name: value.encode() for name, value in needles.items() if value}
    files = 0
    export = subprocess.Popen(["docker", "export", container], stdout=subprocess.PIPE)
    try:
        assert export.stdout is not None
        with tarfile.open(fileobj=export.stdout, mode="r|") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                data = handle.read()
                files += 1
                for name, value in encoded.items():
                    if value in data:
                        findings[name].append(member.name)
                # Base-image and third-party package files may ship sample keys; the application tree must not.
                if member.name.startswith("app/") and "/node_modules/" not in member.name and PEM_PRIVATE.search(data):
                    findings["private_key_block"].append(member.name)
                if "/.next/" in f"/{member.name}" and b"TEST AUTH FIXTURE" in data:
                    findings["fixture_label_in_web_bundle"].append(member.name)
        export.wait(timeout=600)
    finally:
        if export.poll() is None:  # a failed scan must not leave the export stream running
            export.kill()
            export.wait(timeout=30)
        sh(["docker", "rm", "-f", container], check=False)
    return {"files_scanned": files, "findings": findings, "clean": not any(findings.values())}


def build_context_fingerprint(repo: Path) -> dict[str, Any]:
    """SHA-256 over every (path, file SHA-256) Docker's own .dockerignore handling sends to a build of `repo`.

    Two commits with the same fingerprint give the image builds identical inputs (besides the build arguments).
    """
    with tempfile.TemporaryDirectory() as work:
        probe = Path(work) / "context.Dockerfile"
        probe.write_text("FROM scratch\nCOPY . /context/\n")
        sh(["docker", "buildx", "build", "--no-cache", "--quiet", "-f", str(probe), "--output",
            f"type=local,dest={work}/out", str(repo)], timeout=300)
        root = Path(work) / "out" / "context"
        files = sorted(path for path in root.rglob("*") if path.is_file())
        digest = hashlib.sha256()
        for path in files:
            digest.update(f"{path.relative_to(root)}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode())
        return {"files": len(files), "sha256": digest.hexdigest()}
