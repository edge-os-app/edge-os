"""Entrypoint for the full-process, no-egress P04 local Hermes probe."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


INPUT = Path("/qualification/input.json")
OUTPUT = Path("/qualification/output")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _cgroup_text(name: str) -> str | None:
    try:
        return Path("/sys/fs/cgroup", name).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _attempt_egress() -> dict:
    started = time.monotonic()
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=1.0):
            return {"blocked": False, "reason": "connected", "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except OSError as exc:
        return {
            "blocked": True,
            "reason": type(exc).__name__,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


def _filesystem_checks(task: dict) -> dict:
    try:
        with INPUT.open("a", encoding="utf-8") as stream:
            stream.write("forbidden")
        input_read_only = False
    except OSError:
        input_read_only = True
    try:
        Path("/opt/hermes/rootfs-write-probe").write_text("forbidden", encoding="utf-8")
        root_read_only = False
    except OSError:
        root_read_only = True
    personal_mounts = [
        path for path in (Path("/Users"), Path("/home/host"), Path("/run/host"), Path("/var/run/docker.sock"))
        if path.exists()
    ]
    secrets_in_env = [
        name for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY")
        if os.environ.get(name)
    ]
    output_probe = OUTPUT / "write-probe.txt"
    output_probe.write_text("task-local-output\n", encoding="utf-8")
    cache_root = Path(os.environ["XDG_CACHE_HOME"])
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_marker = cache_root / "owner-agent.marker"
    cache_marker.write_text(f"{task['owner_id']}:{task['agent_id']}\n", encoding="utf-8")
    forbidden = task.get("probe_forbidden", {})
    memory_entries = task.get("memory", {}).get("entries", [])
    source_ids = [source.get("source_id", "") for source in task.get("sources", [])]
    file_ids = [fixture_file.get("file_id", "") for fixture_file in task.get("files", [])]
    return {
        "input_mount_read_only": input_read_only,
        "root_filesystem_read_only": root_read_only,
        "other_job_input_unmounted": not Path("/qualification/other/input.json").exists(),
        "other_job_output_unmounted": not Path("/qualification/other/output").exists(),
        "host_or_docker_mounts_present": personal_mounts,
        "provider_secret_env_names_present": secrets_in_env,
        "task_output_mount_writable": output_probe.read_text(encoding="utf-8").strip() == "task-local-output",
        "task_cache_private_marker": cache_marker.read_text(encoding="utf-8").strip() == f"{task['owner_id']}:{task['agent_id']}",
        "task_cache_path": str(cache_root),
        "forbidden_memory_not_in_task_context": forbidden.get("memory", "") not in memory_entries,
        "forbidden_source_not_in_task_context": forbidden.get("source_id", "") not in source_ids,
        "forbidden_file_not_in_task_context": forbidden.get("file_id", "") not in file_ids,
        "home": os.environ.get("HOME"),
        "hermes_home": os.environ.get("HERMES_HOME"),
        "xdg_config_home": os.environ.get("XDG_CONFIG_HOME"),
    }


def _spawn_child_check() -> dict:
    child = subprocess.run(
        [sys.executable, "-B", "-c", "import os; print(os.getppid(), os.getpid())"],
        check=True, capture_output=True, text=True, timeout=3,
    )
    values = child.stdout.strip().split()
    return {"child_process_created": len(values) == 2, "child_parent_pid": int(values[0]), "child_pid": int(values[1])}


def _record_request(request, mode: str, task: dict) -> tuple[dict, dict]:
    body = json.loads(request.content)
    messages = body.get("messages", [])
    prompt_context = {}
    for message in messages:
        content = message.get("content", "")
        if not isinstance(content, str):
            continue
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed.get("job_id") == task.get("job_id"):
            prompt_context = parsed
            break
    memory_entries = task.get("memory", {}).get("entries", [])
    memory_snapshot_matches = prompt_context.get("memory") == task.get("memory")
    expected_memory = bool(memory_entries) and memory_snapshot_matches
    source_ids = [source.get("source_id", "") for source in task.get("sources", [])]
    source_snapshot_matches = prompt_context.get("sources", []) == task.get("sources", [])
    expected_sources = bool(source_ids) and source_snapshot_matches
    file_ids = [fixture_file.get("file_id", "") for fixture_file in task.get("files", [])]
    file_snapshot_matches = prompt_context.get("files", []) == task.get("files", [])
    expected_files = bool(file_ids) and file_snapshot_matches
    forbidden = task.get("probe_forbidden", {})
    forbidden_memory_absent = forbidden.get("memory", "") not in memory_entries
    forbidden_source_absent = forbidden.get("source_id", "") not in source_ids
    forbidden_file_absent = forbidden.get("file_id", "") not in file_ids
    receipt = {
        "request_url": str(request.url),
        "model": body.get("model"),
        "stream": body.get("stream", False),
        "max_tokens": body.get("max_tokens", body.get("max_completion_tokens")),
        "tool_count": len(body.get("tools") or []),
        "message_count": len(messages),
        "owner_fixture_present": prompt_context.get("owner_id") == task["owner_id"],
        "agent_fixture_present": prompt_context.get("agent_id") == task["agent_id"],
        "memory_version_present": prompt_context.get("memory", {}).get("version") == task.get("memory", {}).get("version"),
        "memory_snapshot_empty": prompt_context.get("memory", {}).get("entries") == [],
        "memory_snapshot_matches": memory_snapshot_matches,
        "only_expected_memory_present": expected_memory,
        "source_snapshot_empty": prompt_context.get("sources") == [],
        "source_snapshot_matches": source_snapshot_matches,
        "only_expected_source_present": expected_sources,
        "file_snapshot_empty": prompt_context.get("files") == [],
        "file_snapshot_matches": file_snapshot_matches,
        "only_expected_file_present": expected_files,
        "forbidden_memory_absent": forbidden_memory_absent,
        "forbidden_source_absent": forbidden_source_absent,
        "forbidden_file_absent": forbidden_file_absent,
        "authorization_header_present": bool(request.headers.get("authorization")),
        "real_http_socket_used": False,
    }
    if mode == "truncated":
        receipt["response_finish_reason"] = "length"
    requests_path = OUTPUT / "fake-provider-requests.jsonl"
    with requests_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, sort_keys=True) + "\n")
    if mode == "cancel":
        (OUTPUT / "provider-started.marker").write_text("fake provider entered\n", encoding="utf-8")
        time.sleep(300)
    import httpx
    if mode == "error":
        return receipt, httpx.Response(
            503, json={"error": {"message": "fixture provider unavailable", "type": "server_error"}}
        )
    if mode == "truncated":
        response = {
            "id": "chatcmpl-p04-local-fake-truncated",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "fixture-model"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "{\"operation_id\":"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 24, "completion_tokens": 128, "total_tokens": 152},
        }
        return receipt, response
    outcome = {
        "operation_id": "p04-local-fake-outcome",
        "stage": "VALIDATION",
        "outcome": "UNRESOLVED",
        "code": "unresolved",
        "findings": [{
            "code": "missing_dependency",
            "path": "/market/research_binding",
            "detail": "qualified endpoint prices are unavailable.",
        }],
        "retry": "NOT_RETRYABLE",
        "intake_record_id": "10000000-0000-4000-8000-000000000001",
    }
    response = {
        "id": "chatcmpl-p04-local-fake",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "fixture-model"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(outcome)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 24, "completion_tokens": 40, "total_tokens": 64},
    }
    return receipt, response


class ProviderRequestGuard:
    """Reject Hermes continuation/summary calls before the fake provider does work."""

    def __init__(self, task: dict, mode: str, output: Path, *, max_requests: int = 1, max_tokens: int = 128):
        self.task = task
        self.mode = mode
        self.output = output
        self.max_requests = max_requests
        self.max_tokens = max_tokens
        self.attempt_count = 0
        self.provider_work_count = 0
        self.truncation_seen = False
        self.rejections: list[dict] = []

    @staticmethod
    def _phase(messages: list[dict]) -> str:
        content = "\n".join(str(message.get("content", "")) for message in messages)
        if "summarizing what you've found and accomplished so far" in content:
            return "iteration_summary"
        if "Continue exactly where you left off" in content:
            return "truncation_continuation"
        return "initial"

    def __call__(self, request):
        import httpx

        body = json.loads(request.content)
        messages = body.get("messages", [])
        requested_tokens = body.get("max_tokens", body.get("max_completion_tokens"))
        self.attempt_count += 1
        phase = self._phase(messages)
        reason = None
        if type(requested_tokens) is not int or requested_tokens <= 0 or requested_tokens > self.max_tokens:
            reason = "output_request_limit_exceeded"
        elif self.provider_work_count >= self.max_requests:
            reason = "physical_request_count_exceeded"

        if reason:
            rejection = {
                "attempt": self.attempt_count,
                "phase": phase,
                "requested_max_tokens": requested_tokens,
                "accepted": False,
                "rejection_reason": reason,
                "provider_work_performed": False,
            }
            self.rejections.append(rejection)
            self._append_attempt(rejection)
            return httpx.Response(
                429,
                json={"error": {"message": "local qualification request bound rejected this call", "type": "request_not_admitted"}},
                request=request,
            )

        self.provider_work_count += 1
        self._append_attempt({
            "attempt": self.attempt_count,
            "phase": phase,
            "requested_max_tokens": requested_tokens,
            "accepted": True,
            "rejection_reason": None,
            "provider_work_performed": True,
        })
        receipt, response = _record_request(request, self.mode, self.task)
        finish_reason = None
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices and isinstance(choices[0], dict):
                finish_reason = choices[0].get("finish_reason")
        if finish_reason == "length":
            self.truncation_seen = True
        if isinstance(response, httpx.Response):
            return httpx.Response(response.status_code, json=response.json(), request=request)
        return httpx.Response(200, json=response, request=request)

    def _append_attempt(self, attempt: dict) -> None:
        with (self.output / "provider-request-attempts.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(attempt, sort_keys=True) + "\n")

    def evidence(self) -> dict:
        return {
            "physical_attempts_seen_by_local_guard": self.attempt_count,
            "provider_work_count": self.provider_work_count,
            "request_limit": self.max_requests,
            "output_token_limit": self.max_tokens,
            "truncation_seen": self.truncation_seen,
            "rejections": self.rejections,
        }


def _run_hermes(task: dict, mode: str) -> dict:
    home = Path(os.environ["HERMES_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    config = home / "config.yaml"
    config.write_text(
        "agent:\n  api_max_retries: 1\n  auto_recovery_cycles: 0\n  environment_probe: false\n"
        "model:\n  streaming: false\ncompression:\n  enabled: false\n",
        encoding="utf-8",
    )
    prompt_task = {key: task.get(key) for key in ("owner_id", "agent_id", "job_id", "memory", "sources", "files")}
    task_text = json.dumps(prompt_task, sort_keys=True, separators=(",", ":"))
    system = (
        "You are a P04 local qualification fixture. Return one P02-compatible Outcome JSON object. "
        "Do not call tools or claim production isolation. The task context is fixture data."
    )
    provider_guard = ProviderRequestGuard(task, mode, OUTPUT)

    import httpx
    from openai import OpenAI
    from run_agent import AIAgent

    agent = AIAgent(
        base_url="https://fake-provider.invalid/v1",
        api_key="fixture-only-not-a-secret",
        provider="openrouter",
        model="openai/gpt-6.1-sol",
        max_iterations=task.get("max_iterations", 2),
        max_tokens=128,
        enabled_toolsets=[],
        save_trajectories=False,
        quiet_mode=True,
        session_id=f"p04-{task['job_id']}",
        skip_context_files=True,
        skip_memory=True,
        skip_background_review=True,
        fallback_model=None,
        run_budget_seconds=20,
    )
    agent._api_max_retries = 1
    agent._auto_recovery_cycles = 0
    agent._disable_streaming = True
    fake_client = OpenAI(
        api_key="fixture-only-not-a-secret",
        base_url="https://fake-provider.invalid/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(provider_guard), timeout=5),
    )
    agent._create_request_openai_client = lambda **_: fake_client
    agent._close_request_openai_client = lambda *_args, **_kwargs: None
    agent.client = fake_client
    try:
        try:
            result = agent.run_conversation(
                user_message=task_text,
                system_message=system,
                conversation_history=None,
                task_id=task["job_id"],
            )
        except Exception as exc:
            return {
                "status": "raised",
                "error_class": type(exc).__name__,
                "interrupted": False,
                "failed": True,
                "partial": provider_guard.truncation_seen,
                "failure_reason": "truncated" if provider_guard.truncation_seen else "provider_error",
                "tools_effective": [item.get("function", {}).get("name") for item in (agent.tools or [])],
                "agent_max_iterations": agent.max_iterations,
                "agent_max_tokens": agent.max_tokens,
                "api_max_retries": agent._api_max_retries,
                "auto_recovery_cycles": agent._auto_recovery_cycles,
                "streaming_disabled": agent._disable_streaming,
                "skip_memory_effective": agent._memory_store is None and not agent._memory_enabled,
                "skip_context_files": agent.skip_context_files,
                "skip_background_review": agent.skip_background_review,
                "fallback_count": len(getattr(agent, "_fallback_chain", []) or []),
                "fake_request_count": provider_guard.provider_work_count,
                "provider_request_guard": provider_guard.evidence(),
            }
        final_response = result.get("final_response") if isinstance(result, dict) else None
        truncated = provider_guard.truncation_seen
        rejected = bool(provider_guard.rejections)
        return {
            "status": "TRUNCATED_PARTIAL" if truncated else "returned",
            "final_response": final_response,
            "interrupted": bool(result.get("interrupted")) if isinstance(result, dict) else False,
            "failed": (bool(result.get("failed")) if isinstance(result, dict) else False) or truncated or rejected,
            "partial": truncated,
            "failure_reason": "truncated" if truncated else ("request_rejected" if rejected else None),
            "tools_effective": [item.get("function", {}).get("name") for item in (agent.tools or [])],
            "agent_max_iterations": agent.max_iterations,
            "agent_max_tokens": agent.max_tokens,
            "api_max_retries": agent._api_max_retries,
            "auto_recovery_cycles": agent._auto_recovery_cycles,
            "streaming_disabled": agent._disable_streaming,
            "skip_memory_effective": agent._memory_store is None and not agent._memory_enabled,
            "skip_context_files": agent.skip_context_files,
            "skip_background_review": agent.skip_background_review,
            "fallback_count": len(getattr(agent, "_fallback_chain", []) or []),
            "fake_request_count": provider_guard.provider_work_count,
            "provider_request_guard": provider_guard.evidence(),
        }
    finally:
        try:
            agent.close()
        except Exception:
            fake_client.close()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    task = json.loads(INPUT.read_text(encoding="utf-8"))
    assert os.environ.get("HERMES_HOME", "").startswith("/tmp/p04-")
    sandbox = {
        "filesystem": _filesystem_checks(task),
        "network": _attempt_egress(),
        "process": _spawn_child_check(),
        "cgroup": {
            "memory_max": _cgroup_text("memory.max"),
            "cpu_max": _cgroup_text("cpu.max"),
            "pids_max": _cgroup_text("pids.max"),
            "pids_current": _cgroup_text("pids.current"),
        },
    }
    mode = str(task.get("mode", "normal"))
    hermes = _run_hermes(task, mode)
    _write_json(OUTPUT / "container-result.json", {
        "fixture_label": "LOCAL_FAKE_PROVIDER_NO_NETWORK",
        "hermes_source_commit": "54bc5e509c985f37265c3d416bd2c64b10fc77ba",
        "job_id": task["job_id"],
        "owner_id": task["owner_id"],
        "agent_id": task["agent_id"],
        "memory_version": task["memory"]["version"],
        "sandbox": sandbox,
        "hermes": hermes,
    })
    return 0 if sandbox["filesystem"]["input_mount_read_only"] and sandbox["network"]["blocked"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
