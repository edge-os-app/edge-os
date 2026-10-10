# Model-aware dispatch prompts

Builder requested these provider-specific templates on 2026-10-07. They adapt wording for the observed host/model. The accepted task, source requirements, authority and review procedure remain unchanged.

## Select before dispatch

1. During pre-dispatch activation, read the destination's host/model/effort. Use the existing safe pane procedure. A lane number does not identify a provider.
2. Perform the required fresh-session reset. Recheck the selection because reset can change it. Preserve pane settings under [the controller rule](controller-workflow.md#preserve-pane-model-selections). Report a reset mismatch rather than opening the model picker automatically.
3. Select the profile below using the confirmed configuration. Record host/model/effort, profile, source URLs and date in the dispatch ledger.
4. Fill the common task packet with exact scope, owned paths, accepted sources, relevant prior research, required skills, checks and reply destinations.
   Follow [skill discovery and packet checks](implementation-standards.md) using the full current available catalog and common worker/gate templates. Record selected instruction paths, applicability reasons, responsibility-based filenames and workflow-specific adaptations in the packet and ledger.
5. Include [Ponytail Lite](implementation-standards.md#ponytail-lite-in-future-prompts) in future implementation/repair packets and its completeness checks in review briefs. Preserve task-specific skills and required verification.
6. Add only the matching wording block. Finalize the packet after the post-reset check, then use the assignment's recorded transport. Pane assignments use checked Smux delivery; contributor PR/report and native returns follow their recorded routes.

These are controller activation checks, not ongoing model telemetry or gate receipt auditing. Never interrupt an active task to select a prompt. Use an already compatible selection without changing it. If it conflicts with the approved task route, report the observed mismatch. Pane model/effort/speed changes require an explicit builder instruction, including changes after reset. Choose the wording for the observed model, not a model for the wording.

| Confirmed destination | Guidance to use | Profile |
|---|---|---|
| OpenAI model in Codex, including prescribed Luna implementation and Sol review routes | [Requested ChatGPT guidance](https://help.openai.com/en/articles/10032626-prompt-engineering-best-practices-for-chatgpt), with [reasoning guidance](https://developers.openai.com/api/docs/guides/reasoning-best-practices) where applicable | `openai-scoped-v1` |
| Claude Code with Sonnet 5.5 | [Requested Sonnet 5.5 guidance](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5) | `claude-sonnet-5.5-scoped-v1` |
| OpenCode with an approved DeepSeek implementation or GLM review selection | Retrieve current official guidance for the observed provider/model, plus [OpenCode agent documentation](https://opencode.ai/docs/agents/). If exact-model guidance is unavailable, use the common scoped packet and disclose that limitation; do not invent benchmark claims. | `opencode-scoped-v1`, with actual provider/model and source date recorded |
| A different Claude model or another host | Retrieve current official guidance for that exact model. Use [general Claude guidance](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) only as a disclosed general fallback | Record the actual source and scope. Do not label it Sonnet 5.5 guidance. |

Sources were opened on 2026-10-07. The OpenAI article is general ChatGPT advice, not a Luna/Sol-specific benchmark. Context7 resolved `/websites/developers_openai` and `/websites/platform_claude_en`; its returned examples do not override the directly opened model guide. Recheck relevant official guidance when the selected model or documented behavior changes. An unavailable optional guide is a disclosed limitation, not permission to invent model-specific advice.

## OpenAI wording

Use short Markdown sections separating Task, Accepted sources, Scope and authority, Checks, Reviews and Return. Lead with the observable outcome. Add an example only when it resolves a concrete ambiguity.

```text
Complete the assigned outcome within the named ownership and authority.
Use the accepted sources and required prior research before making material decisions.
Choose the smallest implementation that meets the stated success and failure checks.
Run the required checks and report commands, results and limits.
Continue routine in-scope repairs through the prescribed review process.
Report a specific obstruction when authority, capacity or a required decision prevents progress.
Return the exact candidate, evidence and concise decision reasons. Do not expose private reasoning.
```

The reasoning guide supports direct instructions, clear boundaries and success criteria. Do not add a request for step-by-step private reasoning or unnecessary example chains. This wording is an Edge OS adaptation, not proof of better performance on every OpenAI model.

## Claude Sonnet 5.5 wording

Keep the common packet's sections. State the requested outcome directly, then clarify continuation, scope and verification.

```text
Carry the assigned task through implementation, required checks and the prescribed reviews.
Resolve routine questions from the named sources rather than asking whether to continue.
Pause only for the recorded authority, capacity, safety or missing-decision boundaries.
Keep changes within scope. Required tests, verification instructions and the existing two reviews are part of this task.
For executable changes, run a real check exercising the behavior.
A syntax check or a command that could not start does not prove completion.
Report unavailable checks and their reasons. Stop after the required outcome and handoff.
```

This adapts the guide's continuation, scope and coding-verification advice. Existing task restrictions still govern dependency installation and tool use. The guide's example install advice grants no installation permission. Its suggestions for effort, API token limits or extra review agents do not change our approved configuration or review count.

## Shared rules for both profiles

Use evidence-first task context and the common worker/gate packet. Material behavior follows accepted requirements, not provider prompting advice. Keep private material separate from instructions and publish only permitted inputs.

Workers retain exactly two independent internal reviewers and uncapped internal repairs until both PASS one candidate before the first gate verdict. Later gate repairs follow [gate-stage repair review](controller-workflow.md#gate-stage-repair-review), with a recorded amendment for an active task. Preserve original report/commit identities. Gates retain their own role and three-verdict limit. A gate packet uses the gate's observed model and review output, even if its worker uses another provider. Neither profile authorizes another pair, retrospective duplicate review, paid work, provider calls, financial actions or merge.

Progress notes remain in the agent's own pane and durable evidence. They do not become routine controller pings or permission to poll. Return evidence and concise explanations, not private model reasoning.

## Completion check

Before sending, confirm that the packet records the observed model and profile, exact inputs, requested outcome, checks, existing review policy and reply destinations. Check that its guidance matches the host without changing task authority. Record this check with the immutable packet hash. These document checks do not prove an implementation ran or that a profile is faster.
