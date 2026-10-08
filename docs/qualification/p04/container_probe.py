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
    fixture_payload = json.dumps({key: task[key] for key in ("owner_id", "agent_id", "memory", "sources")})
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
        "forbidden_owner_memory_not_in_task_context": forbidden.get("memory", "") not in fixture_payload,
        "forbidden_owner_source_not_in_task_context": forbidden.get("source_id", "") not in fixture_payload,
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
    text = "\n".join(str(message.get("content", "")) for message in messages)
    receipt = {
        "request_url": str(request.url),
        "model": body.get("model"),
        "stream": body.get("stream", False),
        "max_tokens": body.get("max_tokens", body.get("max_completion_tokens")),
        "tool_count": len(body.get("tools") or []),
        "message_count": len(messages),
        "owner_fixture_present": task["owner_id"] in text,
        "agent_fixture_present": task["agent_id"] in text,
        "only_expected_memory_present": task["memory"]["entries"][0] in text,
        "only_expected_source_present": task["sources"][0]["source_id"] in text,
        "other_owner_memory_absent": task.get("probe_forbidden", {}).get("memory", "") not in text,
        "other_owner_source_absent": task.get("probe_forbidden", {}).get("source_id", "") not in text,
        "authorization_header_present": bool(request.headers.get("authorization")),
        "real_http_socket_used": False,
    }
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


def _run_hermes(task: dict, mode: str) -> dict:
    home = Path(os.environ["HERMES_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    config = home / "config.yaml"
    config.write_text(
        "agent:\n  api_max_retries: 1\n  auto_recovery_cycles: 0\n  environment_probe: false\n"
        "model:\n  streaming: false\ncompression:\n  enabled: false\n",
        encoding="utf-8",
    )
    prompt_task = {key: task[key] for key in ("owner_id", "agent_id", "job_id", "memory", "sources")}
    task_text = json.dumps(prompt_task, sort_keys=True, separators=(",", ":"))
    system = (
        "You are a P04 local qualification fixture. Return one P02-compatible Outcome JSON object. "
        "Do not call tools or claim production isolation. The task context is fixture data."
    )
    request_receipts: list[dict] = []

    def handler(request):
        receipt, response = _record_request(request, mode, task)
        request_receipts.append(receipt)
        import httpx
        if isinstance(response, httpx.Response):
            return httpx.Response(response.status_code, json=response.json(), request=request)
        return httpx.Response(200, json=response, request=request)

    import httpx
    from openai import OpenAI
    from run_agent import AIAgent

    agent = AIAgent(
        base_url="https://fake-provider.invalid/v1",
        api_key="fixture-only-not-a-secret",
        provider="openrouter",
        model="openai/gpt-6.1-sol",
        max_iterations=2,
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
        http_client=httpx.Client(transport=httpx.MockTransport(handler), timeout=5),
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
                "fake_request_count": len(request_receipts),
            }
        final_response = result.get("final_response") if isinstance(result, dict) else None
        return {
            "status": "returned",
            "final_response": final_response,
            "interrupted": bool(result.get("interrupted")) if isinstance(result, dict) else False,
            "failed": bool(result.get("failed")) if isinstance(result, dict) else False,
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
            "fake_request_count": len(request_receipts),
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
