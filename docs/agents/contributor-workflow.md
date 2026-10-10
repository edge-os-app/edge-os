# Contributor workflow

Updated 2026-10-10. This guide makes the existing process usable from your own clone. [Controller workflow](controller-workflow.md) controls review, repairs, evidence and integration; [current ownership](../EDGE_OS_COMPASS_WORKFLOW.md#9-team-ownership) controls responsibilities. This guide assigns no ticket.

## Start from your clone

1. Read [AGENTS.md](../../AGENTS.md), the [README](../../README.md), [team handoff](../CONTROLLER_HANDOFF.md) and your assigned issue. Quant contributors also read the [brief](../team/QUANT_CONTRIBUTOR_BRIEF.md).
2. Use the README's locked toolchains and setup/verification commands. Read the relevant contracts, accepted profiles, numerical examples and tests before proposing behavior. Private courses, controller reports and the builder's machine are not required inputs.
3. For the proposed P14 work, return a profile outline and one independently calculated accounting trace first. Do not change application code until the profile is accepted and the controller supplies an implementation packet.
4. Before implementation, obtain the exact accepted base SHA, task branch, clone/worktree path, owned files, forbidden/shared files, acceptance checks, review route and return destination. Verify the actual path, branch and HEAD before editing. One writer owns each checkout.
5. Select one [execution profile](execution-workflows.md), or record contributor PR/report transport under [portable contributor use](controller-workflow.md#portable-contributor-use). Model names, subscriptions and tmux are not prerequisites for the initial proposal. An implementation assignment still needs an available, explicitly selected review route.

The builder handles the hackathon release candidate. Your assigned wider-product work must remain outside its active leases and must not become a release dependency without an accepted scope change.

## Skills in your agent environment

The repository does not install contributor skills. Inspect your host's available catalog and install or make the selected instruction files available before using them. Record the actual local instruction path and version/source revision in the assignment. Use your host's supported installation mechanism; do not copy the builder's absolute paths, credentials or entire private configuration.

| Concern | Select relevant instructions |
|---|---|
| Accepted ticket execution | Matt's `implement`; `implement-spec` only when coordinating an explicitly approved dependency batch. [Upstream skills](https://github.com/mattpocock/skills). Apply our project adaptations. |
| Implementation discipline | `karpathy-guidelines`, `ponytail` at Lite level, and task-specific design/testing skills. [Implementation standards](implementation-standards.md) contain the required minimum scope and completeness rules. |
| Quantitative work | `quantitative-research`, plus applicable numerical testing/performance guidance. Accepted calculation conventions and independent fixtures control behavior. |
| Python changes | Select the applicable Python/design skills from [the task-routing table](implementation-standards.md#select-relevant-skills-before-every-dispatch), rather than loading every skill for every task. |
| Independent review | `general-review-protocol`, `review-verification-protocol`, `code-reviewer`, `code-review-excellence`, and applicable domain skills. The worker reads Matt's `code-review` for the [adapted A/B assignments](controller-workflow.md#adapted-matt-internal-review). |
| Application verification | Read [verify-edge-os](../../.agents/skills/verify-edge-os/SKILL.md) when assigned. Its fixture recipe does not prove wallet, signing or funded execution. Use the [verification cadence](controller-workflow.md#verification-cadence). |
| Writing | `no-ai-slop` and `unslop` for clear records; `writing-for-agents` for agent instructions. Preserve uncertainty and permission limits. |

Missing skills must be reported before work relies on them. The controller supplies an approved instruction source or records a permitted adaptation. Never claim a skill ran because its name appeared in a prompt. Required unavailable review instructions or checks prevent approval; do not silently substitute a weaker route.

## Ticket sequence

1. Implement only the accepted assignment, with focused tests after meaningful changes. Use responsibility-based filenames and functions. An outside-scope upstream defect is reproduced and proposed to the controller before editing; [the defect procedure](controller-workflow.md#upstream-defects-found-downstream) also applies to already integrated code.
2. Commit a clean candidate and run the complete task-required submission checks on that exact candidate. Preserve commands, results, configuration/input identities and limitations. Keep secrets and private logs out of source control.
3. Obtain the two original independent internal assessments on that candidate. A checks specification/correctness; B checks standards/maintainability and adversarial failure paths. Neither sees the other's initial findings. Repair verified blockers and repeat both reviews until both PASS before the first gate verdict. Internal rounds have no numeric cap.
4. Send the exact candidate, original reports and evidence to the assigned independent gate. It retains the ticket's history and has at most three verdicts. Later repairs follow [gate-stage repair review](controller-workflow.md#gate-stage-repair-review); baseline PASS reports never approve later commits.
5. After gate PASS, the controller checks the proved scope and integrates accepted work serially. Run affected integration checks and record the result. The builder retains main-merge control. Publication, integration, deployment and live financial qualification are separate states.

For PR/report transport, use the assigned PR or issue for the return and provide original sanitized reports as committed artifacts or attachments, as authorized. Do not replace a reviewer's report with your own PASS summary. A teammate does not need to relay pane messages. The controller arranges the separate gate and records its return.

## Reusable prompts

Fill these templates from the accepted assignment; they are field checklists, not permission to start:

- [Worker activation packet](controller-workflow.md#worker-activation-packet).
- [Internal reviewer A/B packet](templates/internal-review.md).
- [Independent gate activation packet](controller-workflow.md#gate-activation-packet).
- [Host/model wording](dispatch-prompt-profiles.md), selected after checking the actual destination configuration.

Replace pane destinations with the recorded PR/report or native return identity when those routes apply. Mark inapplicable Goal, pane activation and Smux fields explicitly. Do not drop task authority, exact commits, ownership, skills, checks or review history.

## Optional agent coordination

The [tmux-goal profile](tmux-goal-workflow.md) uses worker Goals and event-driven gate/controller messages. A gate needs no perpetual Goal. When no authorized ticket is ready, the controller remains idle rather than polling.

The [native-batch profile](native-batch-workflow.md) gives one Codex coordinator a bounded batch Goal and uses fresh child contexts. A Goal is thread/process-specific; it does not transfer itself to other agents or approve extra operations. OpenCode requires qualification of its actual plugin/configuration, isolated persisted Goal state, two named reviewer contexts and return path before autonomous use. A saved Goal, installed plugin or written prompt alone is not proof of activation or hook protection.

Neither optional route requires the builder's private launchers. Do not copy account-specific MCP keys or state files. Required provider access, paid computation, wallets, signing, delegation and financial operations need separate explicit authority.
