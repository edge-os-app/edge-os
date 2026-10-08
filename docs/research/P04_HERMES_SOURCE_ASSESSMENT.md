# P04 Hermes source assessment

Research date: 2026-10-07; local qualification supplement: 2026-10-08. This assessment distinguishes source behavior from measured local fixture behavior and proposed Edge OS controls. The pinned source was installed only inside task-local temporary Docker images for the supplement. One authorized read-only OpenRouter key-control request was made; no provider inference was sent, and no account setting was changed.

## Pinned Hermes source

Inspected `/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent/` at `54bc5e509c985f37265c3d416bd2c64b10fc77ba`. The checkout was clean on `main`; it matched the Probe A commit. Hermes is MIT licensed. Relevant pins:

| File | SHA-256 | Source observation |
|---|---|---|
| `pyproject.toml` | `d09cd0a47109e5abb9abeb326224208b857faa0d1e921c515d7f0bc6031d2d73` | Declares `requires-python = ">=3.11,<3.15"`; compatibility comment says current support is Python 3.14. Core package versions are deliberately pinned. |
| `uv.lock` | `de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01` | Exact resolved dependency set for this source pin. |
| `LICENSE` | `821556e6336796450ab852d375117b48a4887e71d255794fd6318d99982a5ab6` | MIT. |
| `website/docs/guides/python-library.md` | Pinned in Git commit above | Checkout plus PM activation is the documented embed path; no supported wheel/sdist. Documents one AIAgent per task, `run_conversation`, toolsets, memory/context toggles and iteration cap. |
| `run_agent.py`, `agent/turn_facade.py`, `agent/conversation_loop.py` | Pinned in Git commit above | Constructor defaults, blocking one-turn call, task/session identifiers and response lifecycle. |
| `agent/interrupt_control.py`, `agent/chat_completion_helpers.py` | Pinned in Git commit above | Interrupt and stream retry/connection behavior. |
| `agent/turn_usage.py` | Pinned in Git commit above | Reads provider `response.usage`, records session token counters and estimates cost when price data exists. Missing usage is explicitly logged unavailable. This is accounting, not admission enforcement. |
| `agent/agent_init.py` | Pinned in Git commit above | Default memory/context behavior, fallback chain initialization and configured retry behavior. |
| `tools/web_tools.py` | Pinned in Git commit above | The `web` toolset registers `web_search` and `web_extract`; extraction accepts arbitrary URLs. |

The docs say the iteration default is 500; the pinned constructor default is `sys.maxsize`. Treat that mismatch as a reason to pass an explicit cap and verify the runtime value. The constructor also defaults context files and memory on, and an unset tool allowlist may expose a broad set of tools. A fresh `session_id` or `task_id` does not establish owner authorization.

`run_conversation()` is synchronous. The Python guide documents `final_response` and `messages`; usage accounting is handled in Hermes' turn loop when provider usage is present. The official architecture describes interruptible calls, but a caller-side interrupt does not prove the remote request stopped. Streaming/tool retries and provider fallback are separate paths; a returned final string alone is not a complete usage or cost record.

## Official documentation checked through Exa and Context7

- Current [Hermes Python library guide](https://hermes-agent.nousresearch.com/docs/guides/python-library): use source checkout/PM; fresh AIAgent per task; explicit `enabled_toolsets`; `skip_memory`, `skip_context_files`, `max_iterations`; `chat()` hides conversation-loop details. The guide's default iteration value differs from the pinned source above.
- Current [Hermes security policy](https://github.com/NousResearch/hermes-agent/security): Hermes describes itself as a single-tenant personal agent and names OS-level isolation as its load-bearing security boundary. A terminal backend confines terminal/file operations, not the entire agent process tree. Whole-process wrapping is the documented posture for untrusted inputs and shared/production use. This rules out treating a tool allowlist or profile ID as containment.
- Current [Hermes architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture) and [agent loop guide](https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop): confirm synchronous orchestration, provider resolution, tools, retries/fallback, callbacks, compression, persistence and interruption layers. These current docs inform research; the inspected source pin controls the candidate.
- Context7 resolved Hermes to `/nousresearch/hermes-agent` (high source reputation) and Python to `/python/cpython`. The Python docs describe `asyncio` subprocess and timeout cleanup, but they do not provide an OS sandbox or provider-cancellation guarantee.
- Context7 resolved OpenRouter to `/openrouterteam/docs` (official docs). Its [limits endpoint](https://openrouter.ai/docs/api_reference/limits) reports a null `limit` as unlimited; the exact authorized GET result retained `limit`, `limit_remaining` and `limit_reset` as null. Model `max_price` routing is not an aggregate key/account cap. The same project key was found to be shared with other projects, so changing its limit would affect those callers; the coordinator owns any dashboard operation and is resolving that scope. No other key or management credential was used.
- Exa fetched the official Hermes Python guide and security policy and searched the official repository for implementation examples. Page paths and observed details are linked above; the pinned local source is the code evidence.

## GitHub task-worker example inspected

Reviewed `rq/rq` commit `bd339ae3d12d94fb9b01013a1c1fd880f7aea93e`, exact files `docs/docs/jobs.md`, `rq/timeouts.py` and `LICENSE`. Its license text is BSD 2-Clause. The job guide gives explicit queued/started/finished/failed/stopped/canceled states, retries and a timeout. The timeout implementation uses `SIGALRM` on Unix and `threading.Timer` with an asynchronous exception on other platforms; neither is a tenant security boundary. RQ requires Redis and is not adopted. Exa could not fetch `rq/worker.py` at that commit during this review, so no claim about its process-per-job implementation is made from that file.

This example supports keeping job state and cancellation outcomes explicit. It does not qualify Hermes isolation, hard resource limits, cancellation of an upstream HTTP request, duplicate billing or customer authorization.

## Edge OS boundary and source status

The accepted specification and build brief require application-owned research records, a validated typed result, owner-scoped jobs/memory/files/cache/stream/cancellation, explicit cost reservation/settlement, and no model authority over quantitative validation or financial actions. P02's `Outcome` record is strict: extra properties are rejected, defined outcomes remain distinct, intake links and findings are required by outcome, and retry classification is explicit. Its checker validates supplied record bundles in memory; it does not prove authenticated server ownership or persistence.

Issue #9 was readable through the configured GitHub CLI. Its older issue body still says `PLANNED` and lists P02 as a blocker. The activation packet supplies the later accepted base (`8706aa2679ed184adf479b5be426d7a48d7ddfde`), says P02 is builder-accepted and locally integrated, and explicitly supersedes that historical status. No issue was edited.

## Qualification boundary

The original P04 fixture suite proves only helper semantics. The repair runner executes pinned Hermes `AIAgent` in whole-process Docker containers using an HTTP mock that never opens a socket. The canonical repair run observed denied egress, no host/Docker mounts, read-only root/input, separate task homes/caches/files/context, empty Hermes tool allowlists, and configured CPU/memory/PID limits visible through cgroups. Two owners and four fixture agents exercised corrected and cleared memory versions, source/file scoping and a MEM-Q04 authority-challenging memory note. The fixed fake output cannot prove real-model instruction resistance. Local admission checks limited provider work to one fake request at at most 128 output tokens and retained/rejected actual Hermes continuation and iteration-summary attempts. Killing a task container produced one uncertain fake attempt, durable local `INTERRUPTED`/`UNKNOWN` state, retained reservation and no replay. Build/inspection/cleanup fault tests retained stage and cleanup outcome. These are local runner results, not production auth/storage, cloud sandbox, live request, upstream cancellation or billing evidence. The authorized OpenRouter key-control GET returned a null/unlimited limit; the same key is shared with other projects, and no cap change or inference call occurred. Exact repair evidence is in `docs/qualification/p04/evidence/p04-b7a0f3a179b9/qualification-result.json`, `docs/qualification/p04/README.md` and `docs/implementation/P04_HERMES_RUNTIME_PROFILE.md`.
