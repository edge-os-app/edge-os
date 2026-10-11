"""Runs one Hermes turn behind the request guard in a disposable no-network container. Controlled provider only.

It reuses the accepted container policy and result mapping of `DockerHermesTurnRunner` and changes two things: the
entrypoint is the guarded job, and the guard policy and a mounted credential file go into the container. The credential
is a file mount, never a command-line value, so it is not in the process list or in `docker inspect` arguments. A result
that echoes the credential is withheld, and the host never writes the credential into evidence.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from docker_turn_runner import HERE, LABEL, DockerHermesTurnRunner
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage
from provider_guard import GuardPolicy

REDACTED = "[REDACTED]"
ENTRYPOINT = "/opt/hermes/.venv/bin/python"


class GuardedDockerTurnRunner(DockerHermesTurnRunner):
    def __init__(self, *, policy: GuardPolicy, credential_file: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.policy, self.credential_file = policy, credential_file

    def _secret(self) -> str | None:
        return self.credential_file.read_text(encoding="utf-8") if self.credential_file else None

    @staticmethod
    def _redact(folder: Path, secret: str) -> bool:
        """Saved evidence never keeps the credential, even when a provider echoes it. True when something was echoed."""
        echoed = False
        for path in folder.rglob("*"):
            if path.is_file() and secret.encode() in path.read_bytes():
                echoed = True
                path.write_text(path.read_text(encoding="utf-8").replace(secret, REDACTED), encoding="utf-8")
        return echoed

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        self.turn_count += 1
        task_dir = self.evidence_dir / f"turn-{self.turn_count:02d}-{turn.attempt_id}"
        output = task_dir / "output"
        output.mkdir(parents=True)
        job = {"attempt_id": turn.attempt_id, "system_prompt": turn.system_prompt, "user_message": turn.user_message,
               "model": turn.model, "route": turn.route, "max_output_tokens": turn.max_output_tokens,
               "run_budget_seconds": self.run_budget_seconds, "provider_script": dict(self.script_for(turn)),
               "forbidden": self.forbidden, "guard": {"policy": {**asdict(self.policy), "required_extra": dict(self.policy.required_extra)}}}
        input_path = task_dir / "input.json"
        input_path.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
        input_path.chmod(0o400)
        name = f"p05-{self.run_id}-{self.turn_count:02d}"
        mounts = [("src", input_path, "/job/input.json", True), ("src", HERE / "guarded_turn_job.py", "/opt/p05guard/guarded_turn_job.py", True),
                  ("src", HERE / "provider_guard.py", "/opt/p05guard/provider_guard.py", True)]
        if self.credential_file is not None:
            mounts.append(("src", self.credential_file, "/job/credential", True))
        argv = ["docker", "run", "--rm", "--name", name, "--label", f"{LABEL}={self.run_id}", "--network=none",
                "--read-only", "--memory=512m", "--memory-swap=512m", "--cpus=1", "--pids-limit=64", "--cap-drop=ALL",
                "--user", f"{os.getuid()}:{os.getgid()}", "--security-opt=no-new-privileges",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--entrypoint", ENTRYPOINT]
        for _, source, target, readonly in mounts:
            argv += ["--mount", f"type=bind,src={source.resolve()},dst={target}" + (",readonly" if readonly else "")]
        argv += ["--mount", f"type=bind,src={output.resolve()},dst=/job/output",
                 "--env", f"HOME=/tmp/p05-{name}/home", "--env", f"HERMES_HOME=/tmp/p05-{name}/hermes-home",
                 "--env", f"XDG_CONFIG_HOME=/tmp/p05-{name}/config", "--env", f"XDG_CACHE_HOME=/tmp/p05-{name}/cache",
                 "--env", "PYTHONDONTWRITEBYTECODE=1", self.image, "-B", "/opt/p05guard/guarded_turn_job.py"]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            stdout, _ = proc.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            lifecycle = self._kill_owned(name, proc)
            if (secret := self._secret()):
                self._redact(output, secret)  # a job that was killed may have left the credential in its evidence
            (task_dir / "container-lifecycle.json").write_text(json.dumps(lifecycle, indent=1) + "\n")
            return HermesTurnResult(status="TIMED_OUT", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="TimeoutExpired")
        secret = self._secret()
        (task_dir / "container-stdout.txt").write_text(stdout.replace(secret, REDACTED) if secret else stdout, encoding="utf-8")
        echoed = bool(secret) and self._redact(output, secret)  # every exit path, not only a clean one
        result_path = output / "container-result.json"
        if proc.returncode != 0 or not result_path.exists():
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerExit")
        raw = json.loads(result_path.read_text(encoding="utf-8"))
        mapped = self._map(raw)
        guard = raw["guard"]
        observed = {**mapped.observed, "guard_admitted": guard["admitted_count"], "guard_seen": guard["seen_count"],
                    "guard_refusal_reasons": sorted({r["reason"] for r in guard["evidence"] if not r["admitted"]})}
        mapped = replace(mapped, observed=observed)
        if echoed:
            return replace(mapped, status="UNKNOWN", text=None, error_class="CredentialEchoed")
        return mapped
