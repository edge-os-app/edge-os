"""Runs one Hermes turn behind the request guard in a disposable no-network container. Controlled provider only.

It reuses the accepted container policy and result mapping of `DockerHermesTurnRunner` and changes two things: the
entrypoint is the guarded job, and the guard policy and a mounted credential file go into the container. The credential
is a file mount, never a command-line value, so it is not in the process list or in `docker inspect` arguments. A result
that echoes the credential is withheld, and the host never writes the credential into evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from docker_turn_runner import HERE, LABEL, DockerHermesTurnRunner
from leak_scan import encodings
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage
from provider_guard import GuardPolicy

REDACTED = "[REDACTED]"
MAX_SCANNED_BYTES = 64 * 1024 * 1024


class EvidenceNotSealed(RuntimeError):
    """Saved evidence could not be proved free of the credential."""
ENTRYPOINT = "/opt/hermes/.venv/bin/python"


class GuardedDockerTurnRunner(DockerHermesTurnRunner):
    def __init__(self, *, policy: GuardPolicy, credential_file: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.policy, self.credential_file = policy, credential_file

    def _secret(self) -> str | None:
        """The credential without the newline that an editor or a secret store adds."""
        return (self.credential_file.read_text(encoding="utf-8").strip() or None) if self.credential_file else None

    @classmethod
    def _redact(cls, folder: Path, secret: str) -> bool:
        """Saved evidence never keeps the credential, even when a provider echoes it. True when something was echoed.

        Works on bytes in every file, rewrites file names, removes links (it never follows one), makes hidden folders and
        read-only files writable first, and deletes what it cannot scan or rewrite. A folder it cannot clear raises
        `EvidenceNotSealed`: evidence that may hold the credential is not kept as if it were clean.
        """
        forms, found = encodings(secret), [False]
        cls._seal_folder(folder, forms, found)
        return found[0]

    @classmethod
    def _seal_folder(cls, folder: Path, forms: list[bytes], found: list[bool]) -> None:
        try:
            folder.chmod(0o700)
            entries = list(os.scandir(folder))
        except OSError as error:
            shutil.rmtree(folder, ignore_errors=True)
            if folder.exists():
                raise EvidenceNotSealed(f"{folder.name} could not be read or removed") from error
            found[0] = True
            return
        for entry in entries:
            path = Path(entry.path)
            try:
                if entry.is_symlink():
                    path.unlink()
                elif entry.is_dir(follow_symlinks=False):
                    cls._seal_folder(path, forms, found)
                else:
                    cls._seal_file(path, forms, found)
            except EvidenceNotSealed:
                raise
            except OSError as error:
                path.unlink(missing_ok=True)
                if path.exists():
                    raise EvidenceNotSealed(f"{path.name} could not be sealed") from error
                found[0] = True
            name = path.name.encode()
            if path.exists() and any(form in name for form in forms):
                found[0] = True
                path.rename(path.with_name(f"redacted-name-{abs(hash(name)) % 10**8}"))

    @staticmethod
    def _seal_file(path: Path, forms: list[bytes], found: list[bool]) -> None:
        path.chmod(0o600)
        if path.stat().st_size > MAX_SCANNED_BYTES:  # too large to scan whole: not kept
            path.unlink()
            found[0] = True
            return
        data = path.read_bytes()
        if any(form in data for form in forms):
            found[0] = True
            for form in forms:
                data = data.replace(form, REDACTED.encode())
            path.write_bytes(data)

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        self.turn_count += 1
        task_dir = self.evidence_dir / f"turn-{self.turn_count:02d}-{turn.attempt_id}"
        (task_dir / "output").mkdir(parents=True)
        try:
            return self._run_container(turn, task_dir)
        finally:  # whatever happened above, nothing that may hold the credential stays in the evidence
            if (secret := self._secret()):
                self._redact(task_dir / "output", secret)

    def _run_container(self, turn: HermesTurn, task_dir: Path) -> HermesTurnResult:
        output = task_dir / "output"
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
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)  # bytes: the output need not be valid text
        try:
            stdout, _ = proc.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            lifecycle = self._kill_owned(name, proc)
            (task_dir / "container-lifecycle.json").write_text(json.dumps(lifecycle, indent=1) + "\n")
            return HermesTurnResult(status="TIMED_OUT", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="TimeoutExpired")
        secret = self._secret()
        scrubbed = stdout
        for form in (encodings(secret) if secret else []):
            scrubbed = scrubbed.replace(form, REDACTED.encode())
        (task_dir / "container-stdout.txt").write_bytes(scrubbed)  # stdout is evidence too
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
