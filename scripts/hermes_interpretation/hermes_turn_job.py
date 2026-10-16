"""Container entrypoint: one ACTUAL pinned-Hermes turn against a LOCAL FAKE provider, with no network.

The fake provider returns the scripted behavior from the input file. It admits one request, and it records every
outgoing request body so a reviewer can see exactly what Hermes sent. This proves runtime mechanics only.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

INPUT = Path("/job/input.json")
OUTPUT = Path("/job/output")
PINNED_HERMES = "54bc5e509c985f37265c3d416bd2c64b10fc77ba"
ADMITTED_REQUESTS = 1
# Where pinned Hermes puts each request field the guard policy requires: top level, or merged from `extra_body`.
TOP_LEVEL_EXTRA = ("stream", "response_format")
BODY_EXTRA = ("provider", "reasoning", "prompt_cache_options")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def attempt_egress() -> dict:
    """A numeric-address connection must fail: the container has no network."""
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
    except OSError as error:
        return {"blocked": True, "error_class": type(error).__name__}
    return {"blocked": False, "error_class": None}


def filesystem_checks() -> dict:
    def denied(path: str, mode: str) -> bool:
        try:
            with open(path, mode):
                return False
        except OSError:
            return True
    return {"input_write_denied": denied(str(INPUT), "ab"), "root_write_denied": denied("/p05-probe", "wb")}


class WireUsage:
    """Reads `usage` from each provider response body at the HTTP boundary, independent of Hermes' own counters.

    Hermes skips its token accounting when a response is cut short, so its counters can hide real usage.
    """

    def __init__(self) -> None:
        self.reports: list[dict] = []

    def __call__(self, response) -> None:
        response.read()
        try:
            usage = response.json().get("usage")
        except (ValueError, AttributeError):
            return
        keys = ("prompt_tokens", "completion_tokens", "total_tokens")
        if isinstance(usage, dict) and all(isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool)
                                           for key in keys):
            self.reports.append({key: usage[key] for key in keys})


class FakeProvider:
    """httpx transport that plays the scripted provider. It never opens a socket."""

    def __init__(self, job: dict) -> None:
        self.job, self.script = job, job["provider_script"]
        self.requests_seen = 0
        self.admitted = 0
        self.rejected: list[dict] = []
        self.finish_reason: str | None = None
        self.admitted_content: str | None = None
        self.sent_usage: dict | None = None
        self.provider_error_sent = False
        (OUTPUT / "requests").mkdir(exist_ok=True)

    @staticmethod
    def phase(messages: list[dict]) -> str:
        text = "\n".join(str(message.get("content", "")) for message in messages)
        if "summarizing what you've found and accomplished so far" in text:
            return "iteration_summary"
        if "Continue exactly where you left off" in text:
            return "truncation_continuation"
        return "initial"

    def __call__(self, request):
        import httpx

        raw = request.content.decode("utf-8")
        body = json.loads(raw)
        self.requests_seen += 1
        n = self.requests_seen
        messages = body.get("messages", [])
        requested = body.get("max_tokens", body.get("max_completion_tokens"))
        write_json(OUTPUT / "requests" / f"request-{n}.json", body)
        receipt = {
            "request": n, "phase": self.phase(messages), "requested_max_tokens": requested,
            "stream": bool(body.get("stream", False)), "tool_count": len(body.get("tools") or []),
            "roles": [m.get("role") for m in messages],
            "forbidden_present": [value for value in self.job["forbidden"] if value in raw],
            # Hermes wraps the system prompt with its own text, so the prompt must appear inside it verbatim.
            "system_contains_prompt": bool(messages) and self.job["system_prompt"] in str(messages[0].get("content", "")),
            "user_message_present_verbatim": any(m.get("content") == self.job["user_message"] for m in messages),
            "system_message_sha256": hashlib.sha256(str(messages[0].get("content", "")).encode()).hexdigest() if messages else None,
            "request_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        }
        self.first_receipt = getattr(self, "first_receipt", None) or receipt
        reject = None
        if requested != self.job["max_output_tokens"]:
            reject = "output_request_not_as_configured"
        elif self.admitted >= ADMITTED_REQUESTS:
            reject = "physical_request_count_exceeded"
        if reject:
            receipt.update(accepted=False, rejection_reason=reject, provider_work_performed=False)
            self.rejected.append(receipt)
            self.append_receipt(receipt)
            return httpx.Response(429, json={"error": {"message": "request not admitted", "type": "request_not_admitted"}},
                                  request=request)
        self.admitted += 1
        receipt.update(accepted=True, rejection_reason=None, provider_work_performed=True)
        self.append_receipt(receipt)
        kind = self.script["kind"]
        if kind == "hang":
            time.sleep(3600)
        if kind == "http_error":
            self.provider_error_sent = True
            return httpx.Response(self.script["status"], json={"error": {"message": self.script["message"],
                                                                         "type": "server_error"}}, request=request)
        self.finish_reason = self.script["finish_reason"]
        self.admitted_content = self.script["content"]
        completion = {"id": "fake-completion-1", "object": "chat.completion", "created": 0, "model": body.get("model"),
                      "choices": [{"index": 0, "message": {"role": "assistant", "content": self.script["content"]},
                                   "finish_reason": self.finish_reason}]}
        if self.script.get("usage") is not None:
            completion["usage"] = self.sent_usage = dict(self.script["usage"])
        return httpx.Response(200, json=completion, request=request)

    @staticmethod
    def append_receipt(receipt: dict) -> None:
        with (OUTPUT / "provider-request-attempts.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, sort_keys=True) + "\n")


def request_options(job: dict) -> dict:
    """The AIAgent options that make Hermes send the request fields the job's guard policy requires, exactly.

    An empty or absent policy adds nothing, so AUTHORED jobs build the same agent as before. A required field this
    mapping does not know is not sent, and the guard then refuses the request before anything leaves the job.
    """
    required = (job.get("guard") or {}).get("policy", {}).get("required_extra") or {}
    overrides = {name: required[name] for name in TOP_LEVEL_EXTRA if name in required}
    body = {name: required[name] for name in BODY_EXTRA if name in required}
    if body:
        overrides["extra_body"] = body
    options: dict = {"request_overrides": overrides} if overrides else {}
    if "reasoning" in required:  # Hermes' own reasoning setting must agree with the routed value it overrides
        options["reasoning_config"] = required["reasoning"]
    return options


def run_hermes(job: dict) -> dict:
    home = Path(os.environ["HERMES_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(
        "agent:\n  api_max_retries: 1\n  auto_recovery_cycles: 0\n  environment_probe: false\n"
        "model:\n  streaming: false\ncompression:\n  enabled: false\n", encoding="utf-8")
    provider = FakeProvider(job)

    import httpx
    from openai import OpenAI
    from run_agent import AIAgent

    agent = AIAgent(
        base_url="https://fake-provider.invalid/v1", api_key="fixture-only-not-a-secret", provider="openrouter",
        model=job["model"], max_iterations=2, max_tokens=job["max_output_tokens"], enabled_toolsets=[],
        save_trajectories=False, quiet_mode=True, session_id=f"p05-{job['attempt_id']}", skip_context_files=True,
        skip_memory=True, skip_background_review=True, fallback_model=None, run_budget_seconds=job["run_budget_seconds"],
        **request_options(job))
    agent._api_max_retries = 1
    agent._auto_recovery_cycles = 0
    agent._disable_streaming = True
    wire_usage = WireUsage()
    fake_client = OpenAI(api_key="fixture-only-not-a-secret", base_url="https://fake-provider.invalid/v1", max_retries=0,
                         http_client=httpx.Client(transport=httpx.MockTransport(provider), timeout=3700,
                                                  event_hooks={"response": [wire_usage]}))
    agent._create_request_openai_client = lambda **_: fake_client
    agent._close_request_openai_client = lambda *_args, **_kwargs: None
    agent.client = fake_client
    raised_class = None
    result: dict = {}
    try:
        result = agent.run_conversation(user_message=job["user_message"], system_message=job["system_prompt"],
                                        conversation_history=None, task_id=job["attempt_id"])
    except Exception as error:  # noqa: BLE001 - record the class only; the message may hold provider detail
        raised_class = type(error).__name__
    finally:
        counters = {"prompt": agent.session_prompt_tokens, "completion": agent.session_completion_tokens,
                    "total": agent.session_total_tokens, "api_calls": agent.session_api_calls}
        observed = {
            "tools_effective": [t.get("function", {}).get("name") for t in (agent.tools or [])],
            "fallback_count": len(getattr(agent, "_fallback_chain", []) or []),
            "streaming_disabled": agent._disable_streaming,
            "skip_memory_effective": agent._memory_store is None and not agent._memory_enabled,
            "skip_context_files": agent.skip_context_files, "skip_background_review": agent.skip_background_review,
            "api_max_retries": agent._api_max_retries, "auto_recovery_cycles": agent._auto_recovery_cycles,
            "max_iterations": agent.max_iterations, "max_tokens": agent.max_tokens,
            "rejected_extra_requests": len(provider.rejected), "hermes_source_commit": PINNED_HERMES}
        first = getattr(provider, "first_receipt", None) or {}
        observed.update(
            wire_system_contains_prompt=first.get("system_contains_prompt"),
            wire_user_message_verbatim=first.get("user_message_present_verbatim"),
            wire_system_message_sha256=first.get("system_message_sha256"), wire_request_sha256=first.get("request_sha256"),
            wire_forbidden_present=first.get("forbidden_present"), wire_tool_count=first.get("tool_count"))
        try:
            agent.close()
        except Exception:  # noqa: BLE001 - closing a fake client must not hide the result
            fake_client.close()
    failed = bool(result.get("failed")) if isinstance(result, dict) else False
    if provider.finish_reason == "length":
        outcome, text = "truncated", provider.admitted_content
    elif provider.provider_error_sent:
        outcome, text = "provider_error", None
    elif raised_class is not None or failed or provider.admitted == 0:
        outcome, text = "raised", None
    else:
        outcome, text = "returned", result.get("final_response")
    wire = wire_usage.reports[0] if len(wire_usage.reports) == 1 else None  # one admitted request, one report
    reported = wire is not None
    return {"outcome": outcome, "text": text, "error_class": raised_class,
            "usage": {"reported": reported, "prompt_tokens": wire["prompt_tokens"] if wire else None,
                      "completion_tokens": wire["completion_tokens"] if wire else None,
                      "total_tokens": wire["total_tokens"] if wire else None, "source": "wire_response_body",
                      "provider_sent": provider.sent_usage, "hermes_counters": counters},
            "request_count": provider.admitted, "hermes_api_calls": counters["api_calls"], "observed": observed,
            "provider_request_attempts": provider.requests_seen}


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    job = json.loads(INPUT.read_text(encoding="utf-8"))
    sandbox = {"network": attempt_egress(), "filesystem": filesystem_checks(),
               "hermes_home_under_tmp": os.environ.get("HERMES_HOME", "").startswith("/tmp/p05-")}
    hermes = run_hermes(job)
    write_json(OUTPUT / "container-result.json", {
        "fixture_label": "LOCAL_FAKE_PROVIDER_NO_NETWORK", "hermes_source_commit": PINNED_HERMES,
        "attempt_id": job["attempt_id"], "sandbox": sandbox, "hermes": hermes})
    return 0 if sandbox["network"]["blocked"] else 3


if __name__ == "__main__":
    sys.exit(main())
