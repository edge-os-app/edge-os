# P04 Hermes runtime and provider profile

Status: candidate profile for P04 review. It records a local qualification design; it does not qualify a hosted Hermes deployment or authorize a provider call.

## Runtime pin

| Item | Candidate | Evidence and limit |
|---|---|---|
| Hermes source | `NousResearch/hermes-agent` commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba` | Same commit used by accepted Probe A. MIT source. |
| Dependency set | Checkout `uv.lock`, SHA-256 `de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01` | `pyproject.toml` SHA-256 `d09cd0a47109e5abb9abeb326224208b857faa0d1e921c515d7f0bc6031d2d73`. The lock was installed from an archive of the pinned source in a disposable Python 3.14 image. Hermes documents a source checkout prepared with its PM workflow; it does not publish a supported wheel or sdist. |
| Python | Python `3.14.x` for this pin; qualification host is `3.14.4`, container is `python:3.14-slim-trixie` | `pyproject.toml` declares `>=3.11,<3.15`, but its compatibility notes say only 3.14 is currently supported. Only the Linux container path was exercised. |
| Invocation | One actual `AIAgent` in a new Docker container per local fixture job, from the pinned checkout's activated environment | The synchronous `run_conversation()` path completed against a local HTTP mock transport. The test exercised containerized owner A and owner B tasks separately. No provider socket was used. This proves this local recipe only, not a hosted runtime. |

The source guide currently describes `max_iterations=500`, while the pinned `run_agent.py` constructor defaults it to `sys.maxsize`. Always pass an explicit limit. The offline profile proposes `max_iterations=4`; actual completion quality and cost at that limit remain unqualified.

The 2026-10-08 local run used `max_iterations=2`, `max_tokens=128`, no Hermes tools, no streaming, `api_max_retries=1` (the pinned loop's single allowed attempt), zero auto-recovery, no fallback, and no auxiliary call paths. Two normal actual-Hermes turns each produced exactly one labelled local fake-provider request and a P02-valid `UNRESOLVED` fixture packet. One injected HTTP 503 produced one request, a failed Hermes result, and no fallback/retry request. These controls and counts are recorded in `docs/qualification/p04/evidence/p04-d47539cd31d6/qualification-result.json`. They are not live-provider evidence or selected production limits.

## Job and model interface

The application, not Hermes or the caller, creates the authenticated job context:

```text
ResearchTask/1 = {
  owner_id, agent_id, job_id,
  question, adopted_settings, preserved_restrictions,
  evidence_scope, research_budget,
  memory_version_used, prompt_version, tool_manifest_version
}
```

`owner_id` comes from verified application auth; `agent_id` is checked against that owner; `job_id` and idempotency are allocated in durable application storage. These IDs select data. They do not grant access. No raw wallet secret, signing key, mandate credential or unrestricted filesystem path enters the prompt.

The Hermes call is one turn:

```python
agent = AIAgent(
    model="openai/gpt-6.1-sol",
    quiet_mode=True,
    max_iterations=4,  # provisional ceiling; output completion still must be checked
    skip_context_files=True,
    skip_memory=True,
    skip_background_review=True,
    save_trajectories=False,
    session_id=job_id,
    enabled_toolsets=["web"],  # candidate for source research only; not a tenancy boundary
)
result = agent.run_conversation(
    user_message=task_json,
    system_message=versioned_system_prompt,
    conversation_history=None,
    task_id=job_id,
)
```

The runtime adapter must hash and record the exact system prompt, serialized `ResearchTask/1`, P02 schema bundle and tool manifest for every attempt. Any stream is keyed to the authenticated `(owner_id, agent_id, job_id, attempt_id)` and delivered only to that job's caller. Do not reuse a stream, agent object, session or mutable context across jobs. Buffer the response until complete validation and durable result storage succeed; then expose the result through the job's owner-scoped read path.

The pinned SDK returns `final_response` and `messages`; its turn loop reads provider response usage when present. The caller validates the entire final response against the P02 typed record contract. Partial streamed output is withheld from durable records and users until whole-response validation passes. Incomplete, malformed or length-limited output is a failed attempt, not a partial success.

The candidate model route copies Probe A's observed setup: OpenRouter to OpenAI, requested `openai/flex`, `openai/gpt-6.1-sol`, low reasoning, strict JSON Schema, `max_tokens=4096`, no fallback and one observed API attempt. Probe A's two calls cost USD 0.021673 and USD 0.028938. This is a comparison baseline, not a production provider choice or spend approval. The exact prompt bytes, P02 schema bundle, Hermes request adapter, and provider parameter compatibility must be versioned and hashed by the first runtime implementation.

## Tools, memory and persistent state

At the pinned source, `enabled_toolsets=["web"]` exposes `web_search` and `web_extract`. It can reach arbitrary public URLs through the configured web backend. It is therefore unsuitable as the final multi-user evidence boundary by itself. The production target is an application-owned evidence gateway with an explicit source/tool allowlist. That gateway does not exist in this ticket. The terminal, file-write, code-execution, browser, MCP, memory, delegation, wallet and trading toolsets stay disabled. An allowlist in Python is defense in depth only; process-level network and filesystem controls provide the boundary.

Use a fresh `HERMES_HOME` per worker process, a fresh task directory, and an environment allowlist. Include only the pinned runtime needs, exact provider credential and approved gateway route. Do not inherit the host's user config, `.env`, memory, sessions, caches, plugin/MCP config, HOME, Docker socket or unrelated credentials. Mount task input read-only and write output only to that job's private directory. Destroy the worker and scratch state when the job ends. A profile/session ID is a routing key, not authorization.

The selected application store owns thin per-agent memory. Proposed `edge-agent-context/1` is a canonical JSON record with trusted `owner_id`, `agent_id`, monotonically increasing `version`, `enabled`, and owner-adopted entries `{id, kind, text, source_refs, adopted_at}`. `kind` is `preference`, `correction` or `lesson`. Model-generated suggestions remain outside the retrieved context until an owner adopts them. A task receives only its authenticated agent's current enabled snapshot and records the version used. Corrections create a new version. Disable stops future retrieval but preserves the record. Clear removes content and source references, creates an empty tombstone version and stops future retrieval. It cannot retract information already sent to an in-flight provider.

Proposed caps for builder review: 16 KiB canonical UTF-8 per active record, at most 32 entries, at most 2 KiB per entry and 8 source references per entry. Keep the last 32 versions while enabled; clear removes the old content and references. These are bounded starting values, not measured product needs. No P04 code implements storage or a production memory service. Memory content cannot modify strategy rules, validation decisions, mandates, balances, positions, pending actions or tool permissions.

Hermes session storage, context files and built-in memory are excluded from the tenant data model. `skip_context_files`, `skip_memory`, no `conversation_history`, no trajectory saving and per-job `HERMES_HOME` reduce accidental reuse. They do not prove OS isolation or erase provider-side retention.

## Failure, cancellation and usage

Hermes `run_conversation()` is synchronous and can be interrupted through the agent API. The application worker still needs its own deadline and process supervisor. On cancellation or timeout, terminate the worker process and remove its private scratch area; on termination failure, mark cleanup pending and do not reuse that worker. Hermes interruption does not prove that an upstream request stopped or stopped accruing charges. A request with no authoritative final usage remains `UNKNOWN` and keeps its reservation. Do not retry it automatically.

Persist job transitions in the application store: `QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCEL_REQUESTED`, then `CANCEL_REQUESTED -> CANCELED | INTERRUPTED`. Commit the validated result before marking a job `SUCCEEDED`. On worker restart, mark every prior `RUNNING` job `INTERRUPTED`, keep its attempt usage `UNKNOWN` and reserved, remove or quarantine its task directory, and require reconciliation before a new attempt. Never replay the provider call as recovery. A late result may settle the original attempt only if its job, attempt and owner keys still match. A canceled or interrupted job with unconfirmed process cleanup stays `CLEANUP_PENDING` and cannot reuse that worker or workspace. Usage settlement is a separate `RESERVED -> SETTLED | UNKNOWN` record. These are proposed application rules; P04 fixtures do not test durable restart recovery.

Record these separately for each job and provider attempt:

- model context capacity and admitted input size;
- requested maximum generated tokens, including reasoning where the route counts them;
- completed/truncated/failed output status;
- tool/model iteration count and each physical provider attempt;
- estimated cost and its source;
- reserved amount, provider-reported tokens/cost and settlement status.

The reservation is not a hard charge ceiling. The provider may omit usage or report it late, and a killed client may leave an upstream request running. Keep unknown charges reserved, stop new admission when the accepted budget cannot cover them, and reconcile before retry. A hard money ceiling needs provider-enforced limits or an explicit builder decision to accept best-effort accounting.

The pinned Hermes paths include API retries, stream reconnects, stream-to-nonstream recovery, fallback providers, compression summaries, iteration-limit summaries and auxiliary model calls. Each can create more provider work than one visible turn. Probe A disabled fallback and retries and observed one API attempt. P04's candidate config must verify every additional path is off or explicitly included in the same attempt reservation. No configuration name is guessed here. Tool-loop iteration limits do not limit retries or auxiliary calls.

## Proposed worker arrangement and evidence state

Smallest arrangement: the existing application persists an idempotent research job, starts one disposable process from the pinned Hermes checkout in a whole-process OS/container sandbox, supplies one scoped task and one per-job `HERMES_HOME`, and stores validated output through owner-scoped application APIs. No AgentOS, LangGraph, Redis/RQ adoption, permanent Hermes server or model-powered background service is selected. The host, queue technology and cloud are not selected. The Hermes security policy says the whole process tree needs OS-level isolation for untrusted input; a container around only terminal tools is insufficient.

| Claim | Current verdict | What remains |
|---|---|---|
| Pinned local source and interface | Actual pinned `AIAgent.run_conversation()` executed in a Python 3.14 Linux container | Only this source pin/image/host combination is qualified. Current upstream docs are not the tested source. |
| P02 result shape | Two actual-Hermes returns from the labelled local fake were checked by the accepted P02 `Outcome` checker | No real provider wire, production result envelope or app adapter was exercised. |
| Memory owner/agent scoping | SQLite fixture survived reopen. Two owners/agents received distinct memory/source snapshots; tests denied cross-owner reads and provider-request receipts excluded the other owner's sentinels. | This is local fixture authorization, not authenticated application storage or concurrent server authorization. |
| Filesystem/context isolation | Whole Hermes process ran in separate Docker containers with no egress, read-only root and input, task-only output mount, no host/Docker mounts, distinct HOME/Hermes/config/cache paths and no effective tools. Actual cgroup values matched the 512 MiB, one-CPU and 64-PID limits. | Local Docker proof only. No deployed host, kernel hardening review, adversarial escape suite or production tenancy proof. |
| Cancellation and cleanup | Host killed a Hermes container during one fake-provider request. Docker removed the whole labeled resource. A reopened SQLite ledger marked the attempt `INTERRUPTED`/`UNKNOWN`, retained its full fixture reservation and refused replay. | This is a local runner and recovery fixture. No application store, real upstream cancellation, or provider settlement was exercised. |
| Network denial | Container's whole-process numeric IPv4 socket attempt failed with egress disabled. The fake OpenAI transport used no real socket. | Does not establish a production firewall or cloud egress policy. |
| Usage reservation and settlement | Existing offline fixture tests and a separate durable SQLite restart ledger retain unknown usage and enforce its local task budget before dispatch. | The live OpenRouter check returned a null/unlimited key limit; remaining account balance and aggregate charge ceiling are unverified. Real price/usage settlement is not qualified. |
| Hosted multi-user suitability | Unqualified | Do not host or enable multi-user Hermes until the actual OS boundary and all owner-scoped paths pass. |

The reproducible local runner and sanitized evidence are in `docs/qualification/p04/`. The successful run is `evidence/p04-d47539cd31d6/qualification-result.json`. The provider-error case also shows the pinned Hermes error string can contain provider detail; the application adapter must redact it. Container process termination does not prove cancellation of an upstream provider request. The local evidence must not be presented as production readiness.

## Remaining checks and authority

1. The pinned local container run, P02 output validation, offline fixture suite, and native runner tests now pass. Repeat them from the committed candidate and retain the new evidence set.
2. Production qualification remains separate. Test authenticated application job/memory/source/stream/cancel paths, durable application restart reconciliation, and the intended deployed whole-process sandbox. The local containers do not make an app or host change and do not qualify a hosted service.
3. A frozen one-request plan exists separately in the controller workspace. The single authorized metadata check on the existing shared project key returned `limit: null`, `limit_remaining: null` and `limit_reset: null`; it does not enforce the USD 2 P04 allowance. Builder authorized a cap operation that the coordinator owns, but that operation is pending and must be verified before any inference. No worker dashboard changes or real inference are authorized here. Even a verified key cap does not prove a canceled upstream request stops billing; retain the full local reservation and never replay an uncertain request.
4. Before choosing deployment, compare the candidate sandbox on the intended host, then record the selected host and its tested CPU, memory, wall-time, disk and network enforcement. P04 selects no paid host or deployment.

No real provider inference, deployment or financial operation occurred for this profile. One authorized read-only OpenRouter key-control request used the existing key route. The exact sanitized result is retained outside the repository; no credential value was logged or copied. Pinned dependencies were installed only inside temporary local Docker images, which were removed after each run.
