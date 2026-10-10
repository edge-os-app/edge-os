"""Runs one Hermes turn in a disposable whole-process container against a local fake provider.

Test support for P05. It implements the adapter's `HermesTurnRunner` boundary with the same container policy as the
accepted P04 local recipe: no network, read-only root, one input file, one output directory, dropped capabilities.
It owns only what it creates: containers and the image carry the run label and are removed by exact name or tag.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage

PINNED_HERMES = "54bc5e509c985f37265c3d416bd2c64b10fc77ba"
HERMES_SOURCE = Path("/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent")
HERE = Path(__file__).resolve().parent
LABEL = "edge-os.test.run"
PYTHON_IMAGE = "python:3.14-slim-trixie@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2"


def docker(*args: str, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, check=check)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PinnedHermesImage:
    """Builds the locked Hermes source into a Python 3.14 image and removes exactly that image afterwards."""

    def __init__(self, run_id: str, workdir: Path) -> None:
        self.run_id, self.workdir, self.tag = run_id, workdir, f"edge-os-p05-hermes:{run_id}"

    def source_identity(self) -> dict[str, Any]:
        """Require the pinned commit with no modified tracked file. Untracked paths are recorded, not trusted.

        The image is built from `git archive` of the pinned commit, so untracked files never enter it.
        """
        def git(*args: str) -> str:
            return subprocess.run(["git", "-C", str(HERMES_SOURCE), *args], capture_output=True, text=True,
                                  check=True).stdout.strip()

        head, modified = git("rev-parse", "HEAD"), git("status", "--porcelain", "--untracked-files=no")
        if head != PINNED_HERMES or modified:
            raise RuntimeError(f"Hermes source is not the pinned commit: head={head} modified_tracked={bool(modified)}")
        untracked = git("status", "--porcelain", "--untracked-files=all").splitlines()
        return {"commit": head, "uv_lock_sha256": sha256_file(HERMES_SOURCE / "uv.lock"),
                "pyproject_sha256": sha256_file(HERMES_SOURCE / "pyproject.toml"), "untracked_paths": untracked}

    def build(self) -> str:
        identity = self.source_identity()
        context = self.workdir / "context"
        (context / "hermes-agent").mkdir(parents=True)
        archive = subprocess.run(["git", "-C", str(HERMES_SOURCE), "archive", "--format=tar", PINNED_HERMES],
                                 capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(context / "hermes-agent")], input=archive, check=True)
        shutil.copy(HERE / "Dockerfile", context / "Dockerfile")
        shutil.copy(HERE / "hermes_turn_job.py", context / "hermes_turn_job.py")
        built = docker("build", "--label", f"{LABEL}={self.run_id}", "-t", self.tag, str(context), timeout=1800,
                       check=False)
        (self.workdir / "docker-build.log").write_text(built.stdout + built.stderr, encoding="utf-8")
        if built.returncode != 0:
            raise RuntimeError(f"image build failed (see docker-build.log): exit {built.returncode}")
        image_id = docker("image", "inspect", self.tag, "--format", "{{.Id}}").stdout.strip()
        (self.workdir / "source_identity.json").write_text(
            json.dumps({**identity, "image_tag": self.tag, "image_id": image_id,
                        "python_image": PYTHON_IMAGE},
                       indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return self.tag

    def remove(self) -> dict[str, Any]:
        """Remove this run's image and report what is left. Only this tag and this run's label are touched."""
        docker("rmi", "-f", self.tag, check=False)
        absent = docker("image", "inspect", self.tag, check=False).returncode != 0
        leftovers = docker("ps", "-a", "--filter", f"label={LABEL}={self.run_id}", "--format", "{{.Names}}",
                           check=False).stdout.split()
        return {"image_tag": self.tag, "image_removed": absent, "labeled_containers_left": leftovers}


class DockerHermesTurnRunner:
    def __init__(self, *, image: str, run_id: str, evidence_dir: Path,
                 script_for: Callable[[HermesTurn], Mapping[str, Any]], forbidden: Sequence[str] = (),
                 timeout_seconds: int = 90, run_budget_seconds: int = 60) -> None:
        self.image, self.run_id, self.evidence_dir = image, run_id, evidence_dir
        self.script_for, self.forbidden = script_for, list(forbidden)
        self.timeout_seconds, self.run_budget_seconds = timeout_seconds, run_budget_seconds
        self.turn_count = 0

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        self.turn_count += 1
        task_dir = self.evidence_dir / f"turn-{self.turn_count:02d}-{turn.attempt_id}"
        output = task_dir / "output"
        output.mkdir(parents=True)
        job = {"attempt_id": turn.attempt_id, "system_prompt": turn.system_prompt, "user_message": turn.user_message,
               "model": turn.model, "route": turn.route, "max_output_tokens": turn.max_output_tokens,
               "run_budget_seconds": self.run_budget_seconds, "provider_script": dict(self.script_for(turn)),
               "forbidden": self.forbidden}
        input_path = task_dir / "input.json"
        input_path.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
        input_path.chmod(0o400)
        name = f"p05-{self.run_id}-{self.turn_count:02d}"
        argv = [
            "docker", "run", "--rm", "--name", name, "--label", f"{LABEL}={self.run_id}", "--network=none",
            "--read-only", "--memory=512m", "--memory-swap=512m", "--cpus=1", "--pids-limit=64", "--cap-drop=ALL",
            "--user", f"{os.getuid()}:{os.getgid()}", "--security-opt=no-new-privileges",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--mount", f"type=bind,src={input_path.resolve()},dst=/job/input.json,readonly",
            "--mount", f"type=bind,src={output.resolve()},dst=/job/output",
            "--env", f"HOME=/tmp/p05-{name}/home", "--env", f"HERMES_HOME=/tmp/p05-{name}/hermes-home",
            "--env", f"XDG_CONFIG_HOME=/tmp/p05-{name}/config", "--env", f"XDG_CACHE_HOME=/tmp/p05-{name}/cache",
            "--env", "PYTHONDONTWRITEBYTECODE=1", self.image]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            stdout, _ = proc.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            lifecycle = self._kill_owned(name, proc)
            (task_dir / "container-lifecycle.json").write_text(json.dumps(lifecycle, indent=1) + "\n")
            return HermesTurnResult(status="TIMED_OUT", text=None, usage=Usage(), request_count=None,
                                    observed={}, error_class="TimeoutExpired")
        (task_dir / "container-stdout.txt").write_text(stdout, encoding="utf-8")  # private evidence only
        result_path = output / "container-result.json"
        if proc.returncode != 0 or not result_path.exists():
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerExit")
        return self._map(json.loads(result_path.read_text(encoding="utf-8")))

    @staticmethod
    def _map(result: dict[str, Any]) -> HermesTurnResult:
        hermes, usage = result["hermes"], result["hermes"]["usage"]
        status = {"returned": "RETURNED", "truncated": "TRUNCATED", "provider_error": "PROVIDER_FAILED"}.get(
            hermes["outcome"], "UNKNOWN")
        reported = Usage(usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"],
                         "PROVIDER_REPORTED") if usage["reported"] else Usage()
        error = "ProviderHTTPError" if status == "PROVIDER_FAILED" else hermes["error_class"]
        observed = {**hermes["observed"], "network_blocked": result["sandbox"]["network"]["blocked"]}
        return HermesTurnResult(status=status, text=hermes["text"], usage=reported, request_count=hermes["request_count"],
                                observed=observed, error_class=error)

    def _kill_owned(self, name: str, proc: subprocess.Popen[str]) -> dict[str, Any]:
        """Kill the container only when its name and run label both match, then reap the client and verify absence."""
        info = docker("inspect", name, "--format", f'{{{{.Name}}}} {{{{index .Config.Labels "{LABEL}"}}}}', check=False)
        owned = info.returncode == 0 and info.stdout.strip() == f"/{name} {self.run_id}"
        if owned:
            docker("kill", name, check=False)
        try:
            proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
        for _ in range(20):
            if not docker("ps", "-a", "--filter", f"name=^{name}$", "-q", check=False).stdout.strip():
                return {"container": name, "ownership_verified": owned, "killed": owned, "container_absent": True}
            time.sleep(0.5)
        return {"container": name, "ownership_verified": owned, "killed": owned, "container_absent": False}
