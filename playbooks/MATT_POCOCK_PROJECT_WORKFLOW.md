# Matt Pocock project workflow

This is the repository-adopted playbook. Workspace playbooks are reusable references; changes to them do not automatically change this project's rules.

**Status:** Reusable project playbook

**Scope:** Move a selected idea, problem, or change through product decisions, evidence gathering, specification, implementation, review, and human acceptance.

**Audience:** Builders and agents working in a repository with the Matt Pocock skills installed.

## What this workflow does

This workflow starts after a person has identified a problem or possible direction worth examining. It helps the person and their agents turn that input into an agreed, tested, and implemented result.

It does not choose markets, prove demand, rank hackathon ideas, or decide whether a business should exist. Use a separate discovery process when the project still needs idea selection or market validation.

The workflow is conditional. Invoke only the steps needed for the current work.

## Source authority

Use this order when instructions disagree:

1. The user's current instruction.
2. The repository's accepted decisions and controlling workflow.
3. The currently installed skill files.
4. Current upstream skill documentation.
5. This generic playbook.
6. Articles, videos, transcripts, and demonstrations.

Installed skill files control their exact current behavior. This playbook explains how the skills fit together. Recheck the installed files after an upgrade.

## Route at a glance

```text
configure the repository once
        |
        v
selected idea, problem, bug, or research finding
        |
        +--> decisions fit one focused session
        |       |
        |       v
        |   /grill-with-docs
        |       |
        |       +--> needs runnable evidence --> /handoff -> /prototype -> return finding
        |       |
        |       +--> small build -----------> /implement
        |       |
        |       `--> multi-session build ---> /to-spec -> /to-tickets
        |
        `--> decisions are broad, dependent, or unclear
                |
                v
            /wayfinder
                |
                +--> research, prototype, grilling, and task decision tickets
                |
                `--> cleared map -> /to-spec -> /to-tickets

/to-tickets
    -> one fresh /implement session per ready ticket
    -> /tdd at the agreed test seams
    -> focused checks during the change
    -> full required test suite
    -> local candidate commit
    -> two independent internal reviews of that candidate against the specification and repository standards
    -> fixes, replacement candidate, and review when needed
    -> controller verifies evidence and updates ticket state
    -> human acceptance
```

## Terms

### Decision work

Work that determines what the product or change should do. Examples include user behavior, scope, state changes, permissions, failure handling, and acceptance criteria.

### Implementation work

Work that builds already accepted behavior. Implementation should not reopen product decisions unless the code exposes a missing or contradictory decision.

### Prototype

Throwaway code or a visual experiment that answers one named question. A prototype is evidence for a decision. It is not an early production implementation.

### Smart zone

The amount of context an agent can use without losing important constraints or making inconsistent decisions. Start a fresh session or create a handoff before the current context becomes unreliable.

### Decision ticket

A Wayfinder ticket that resolves an unknown before specification.

### Implementation ticket

A narrow, testable unit of work created from an accepted specification. Do not mix it with Wayfinder decision tickets.

## Project configuration

Record the following paths before using the workflow. Use the repository's existing conventions when they exist.

```text
Workspace root:
Agent instruction file:
Issue tracker:
Domain document or context map:
ADR directory:
Specification directory:
Prototype directory:
Test commands:
Type-check command:
Lint command:
Build command:
Required review command:
```

The repository configuration is the source of truth for commands and paths. Do not copy values into several documents.

## Approved model policy

Builder approved the Codex route on 2026-10-01 and added the Claude route on 2026-10-06. Choose the worker host according to available subscription capacity. These are operating defaults, not benchmark results. This section is the authoritative model-routing policy.

Builder correction, 2026-10-07: defaults do not authorize changing an existing pane's model, effort or speed. Follow [preserve pane model selections](../docs/agents/controller-workflow.md#preserve-pane-model-selections). Inspect first and use a compatible selection unchanged. Report reset-induced mismatches. Only an explicit builder instruction authorizes a pane-setting change. Fresh internal reviewer launches still use the prescribed route below.

| Host and role | Model | Model selection | Effort | Assignment |
|---|---|---|---|---|
| Codex controller and independent gate | GPT-6.1 Sol | `gpt-6.1-sol` | `high` | Check scope, dependencies, candidate evidence, verified defects and acceptance. The gate remains independent of the worker and its two internal reviewers. |
| Codex implementer | GPT-6 Luna | `gpt-6-luna` | `high` | Implement one accepted bounded ticket with tests and runtime evidence. |
| Codex internal reviewer 1 | GPT-6.1 Sol | `gpt-6.1-sol` | `high` | Check specification compliance, correctness, tests and integration. |
| Codex internal reviewer 2 | GPT-6.1 Sol | `gpt-6.1-sol` | `high` | Check repository standards and maintainability. Challenge assumptions, missing failures, permissions and recovery. Check statistical validity when relevant. |
| OpenCode implementer | DeepSeek Flash | Preserve the explicitly approved provider/model ID | Record actual supported effort | Implement the accepted task; qualify configuration and return route before activation. |
| OpenCode internal reviewers A and B | GLM-5.3 Flash | Explicit provider/model selection in two separate native reviewer contexts | Record actual supported setting | Apply the same A/B assignments; do not replace independence with two passes in one context. |
| Claude implementer | Sonnet | Explicitly select account-available Sonnet and record its exact version | Record actual host-supported effort | Implement the same accepted ticket and verification requirements. |
| Claude internal reviewer 1 | Sonnet | Explicit Sonnet selection in a native reviewer context | Record actual host-supported effort | Check specification compliance, correctness, tests and integration. |
| Claude internal reviewer 2 | Sonnet | Explicit Sonnet selection in a separate native reviewer context | Record actual host-supported effort | Check repository standards and maintainability. Challenge assumptions, missing failures, permissions and recovery. Check statistical validity when relevant. |

Use Standard speed for Codex by default. Luna is not a default reviewer. Claude reviewers must select Sonnet explicitly rather than inherit a possibly different implementer model. The worker explicitly selects the prescribed reviewer model and effort at launch and records the configured selection. Account aliases can change versions.

Builder clarification, 2026-10-07: model selection is the dispatcher's responsibility, not a separate gate audit. Gates do not require original model-dispatch receipts, reviewer self-introspection or inaccessible serving-backend telemetry. A configured Sol 6.1/high review is not blocked because its reviewer cannot independently inspect those settings. Retain both original independent candidate-bound reports, applied skills, checks and verdicts. A concrete reported model substitution must be corrected within the task's existing authority and budget; do not invent a configuration mismatch from unavailable telemetry. This clarification applies to P04's current intake and future reviews. It does not waive technical findings, missing original reviews or review budgets.

For a very difficult Claude ticket, use Opus for one internal reviewer when complex cross-module behavior, consequential ambiguity or repeated failed repairs justify it. Record the reason, bounded review question, available model and review budget before invoking it. Opus is not automatic for every financial ticket or for cosmetic work. The independent Codex gate still checks financial/security boundaries and required qualification evidence. A gate or stronger model cannot substitute for tests or actual provider enforcement.

The builder selected GLM-5.3 Flash for OpenCode internal reviews on 2026-10-10. This does not change the Claude Sonnet or Codex Sol review routes. Provider/model IDs and availability must be verified in the destination environment; the names above do not install or authorize a provider. Preserve active recorded selections and financial limits.

Use native internal reviewers on the active host, followed by the separate Codex gate. Keep OMC disabled for this workflow. The existing tmux lanes and handoff packets are sufficient; this policy installs no orchestrator or cross-provider bridge.

### Implementation and review boundaries

- Give either implementer explicit inputs, outputs, constraints, acceptance behavior and required checks.
- Return missing product decisions to the controller. An implementer must not invent accepted behavior.
- When semantic ambiguity or repeated failed repairs suggest a stronger implementer, report the proposed escalation and reason. An existing pane-model change requires explicit builder instruction. The approved difficult-ticket exception above concerns review, not an automatic implementer switch.
- Record the reason and actual model before the escalated attempt.
- Run each internal review in a separate context from the implementer and the other reviewer.
- Give both reviewers the approved behavior, relevant contracts, exact change, and verification evidence.
- Use the same base and candidate commit for both reviews when the work uses Git.
- For an authorized non-Git task, freeze the changed files and record their checksums instead.
- Keep the other reviewer's findings hidden until each reviewer finishes its initial assessment.
- Record each verdict against the exact reviewed revision.
- After a fix, review the changed scope and affected invariants again. Earlier approval does not cover the replacement revision.
- Two reviewers using the same model can share blind spots. Require reproducible tests and inspectable evidence before acceptance.
- After both internal reviews pass, send the same candidate and evidence to the independent Codex gate. Gate approval cannot replace a missing initial internal review. Later gate-requested repairs follow [gate-stage repair review](../docs/agents/controller-workflow.md#gate-stage-repair-review); preserve the baseline pair and approve only the exact resulting candidate.
- When switching worker hosts, stop the old worker first. Preserve its task, worktree, branch, base, changes, checks and remaining work. The replacement verifies those records before editing. One lane has one active writer.
- Record the new worker host and review route. The replacement candidate needs both internal reviews under that route and the gate's assessment. Preserve earlier reviews as historical evidence.

### Optional escalation and authority

GPT-6 Astra is an optional escalation, not a routine second reviewer. Consider it only for consequential disagreements unresolved by focused tests and source checks.

Obtain builder approval before using Astra. Record the question, scope, effort, and review budget. Record unavailable models as a dispatch blocker rather than silently substituting them.

These defaults conserve usage across the builder's two concurrent hackathons. Keep each project's inputs, state, and approvals separate.

Selecting a model does not authorize implementation, workers, new chats, paid infrastructure, financial actions, or external writes. Existing approval gates remain unchanged.

## Execution policy

Use Matt Pocock's `implement` as the default executor for one accepted ticket. The controller owns scheduling, evidence acceptance, integration, and ticket completion. Reuse approved decisions; ask new planning questions only when a material gap blocks the assigned work.

Choose one executor for each work unit. Record its installed skill path and version or source revision in the task packet. Use the invocation supported by the actual host.

| Route | Use when | Controller boundary |
|---|---|---|
| Matt `implement` | An accepted ticket has clear behavior and test seams. | The Worker implements; the controller audits evidence and advances the frontier. |
| Selected pstack skills | Investigation, a difficult bug, or a contested design needs additional evidence. | Assign a bounded question and artifact; load only the relevant skill and its required references. |
| Full pstack `poteto-mode` | Its task playbook fits an explicitly assigned work unit. | State permitted delegation, commit operations, verification, and PR authority before work starts. |
| Superpowers `executing-plans` | A written plan needs inline execution instead of the default route. | Select it as the alternative executor; retain project ownership and acceptance rules. |

Matt `implement-spec` and Superpowers `subagent-driven-development` provide their own orchestration. Select either as the owner of an approved execution plan, rather than nesting a second scheduler under the controller. A change of executor does not grant merge, publishing, financial, or additional delegation authority.

Use architectural exploration only for unresolved design choices. Use additional review panels when their distinct purpose justifies the cost. Any separate exploration time limit must be explicit. Internal ticket repairs and independent replacement reviews repeat until both PASS on one candidate, without a numeric round cap. Only the independent gate has the three-verdict limit under [the controller review policy](../docs/agents/controller-workflow.md#review-budgets-and-host-changes). Genuine authority, capacity, unsafe-delivery or approved run-limit obstructions remain visible.

## Step 0: configure the repository

Run `/setup-matt-pocock-skills` once when a repository has not been configured for the workflow.

Confirm that setup defines:

- the issue tracker;
- triage labels;
- the domain-document layout;
- the ADR location;
- pointers in `AGENTS.md` or `CLAUDE.md`.

After setup, inspect the repository's scripts, configuration, and continuous-integration files. Record its test, type-check, lint, and build commands in the project configuration above. `/setup-matt-pocock-skills` does not define these commands.

If the repository already has equivalent conventions, preserve them and add only the missing pointers.

Completion condition: a fresh agent can find the tracker, domain rules, ADRs, specifications, and verification commands without relying on conversation history.

## Step 1: establish the starting point

Begin with one of these inputs:

- a selected product idea;
- a user problem;
- a requested feature;
- a defect with evidence;
- a research finding that may require a change.

Record:

```text
Person affected:
Job or outcome:
Current failure or limitation:
Why it matters:
Known constraints:
Available evidence:
Unresolved questions:
Success condition:
```

Use `/research` when a decision requires facts outside the working directory. The research task must name the decision it supports, prefer primary sources, and return one cited artifact.

Research supplies facts. The human still makes consequential product and tradeoff decisions.

Completion condition: the starting problem and desired result are concrete enough to examine, and every material unknown is visible.

If several candidate ideas are still competing, stop this workflow and finish idea selection first.

## Step 2: choose the planning route

Choose one top-level route.

### Use `/grill-with-docs` for a focused decision set

Use it when one strong session can hold the problem and the remaining decisions.

The agent:

- inspects relevant facts and code;
- asks concrete questions;
- tests shared understanding with scenarios;
- records stable language in the domain document;
- records consequential, surprising, and hard-to-reverse decisions in ADRs.

The human makes the material product decisions. The agent must not convert its recommendation into an approved decision.

Completion condition: the problem, vocabulary, required behavior, exclusions, failure handling, and acceptance boundary are agreed. Every remaining unknown has a research or prototype route.

### Use `/grill-me` outside a repository

Use it when no working directory exists. Create a durable handoff before the result enters a repository.

### Use `/wayfinder` for a large decision space

Use it when the destination is recognizable but the decisions are too broad, dependent, or unclear for one focused session.

Wayfinder is justified by decision complexity. A project does not need Wayfinder merely because implementation will require several tickets.

Completion condition: one route is selected. Do not run `/grill-with-docs` and `/wayfinder` over the same settled questions.

## Step 3: raise fidelity only when needed

Use discussion when the team can decide safely from examples and existing evidence.

Use `/prototype` when the decision needs something runnable or visible, such as:

- an interface behavior;
- a state model;
- an external integration;
- a performance assumption;
- a risky technical claim;
- an unfamiliar user interaction.

Before prototyping, freeze:

```text
Question:
Why the answer matters:
Inputs held constant:
Smallest runnable test:
Evidence to capture:
Pass condition:
Narrow condition:
Reject condition:
Excluded work:
```

When the prototype needs a separate directory, branch, tool, or session, use `/handoff`. Return the observations and verdict to the original decision session.

Keep useful evidence. Discard accidental architecture and production shortcuts.

Completion condition: the prototype answers its frozen question with inspectable evidence. Stop prototyping when the question has an answer.

## Step 4: run Wayfinder when selected

Skip this step when `/grill-with-docs` is sufficient.

### Chart the map

Use one session to:

1. Define the destination.
2. Explore the decision space broadly.
3. Create the map as an index.
4. Create precise decision tickets.
5. Add blocking relationships after ticket identities exist.
6. Put unclear but relevant questions under `Not yet specified`.
7. Put deliberate exclusions under `Out of scope`.
8. Start independent research in parallel when useful.
9. Stop after charting.

Do not resolve a non-research decision ticket during the charting session.

### Use the correct ticket type

| Ticket type | Normal participation | Result |
|---|---|---|
| `research` | Agent works independently | A sourced fact or evidence artifact |
| `prototype` | Human reviews evidence | An answer to a runnable or visual question |
| `grilling` | Human participates | An accepted product decision |
| `task` | Depends on the task | Work required before another decision |

### Resolve the frontier

For each non-research ticket:

1. Start a fresh session.
2. Read the map at low detail.
3. Select one open, unblocked ticket.
4. Claim it before work starts.
5. Read only the related detail.
6. Resolve that one decision with the required human participation.
7. Write the answer into the ticket.
8. Mark the ticket resolved.
9. Add a short linked decision summary to the map.
10. Add any newly exposed ticket or exclusion.
11. Stop the session.

Independent research tickets may run in parallel. The controller must still audit their evidence before treating them as resolved.

### Clear the map

The map is clear when:

- the destination is reached;
- no open ticket blocks the specification;
- `Not yet specified` contains no question that can now become a ticket;
- each durable decision has one detailed source;
- the map links each detailed decision instead of copying it;
- excluded work is explicit.

Wayfinder produces decisions. It does not implement the product.

## Step 5: choose the build handoff

After `/grill-with-docs`:

- use `/implement` in the same context when the change is small and the context remains reliable;
- use `/to-spec` and `/to-tickets` when the build requires several fresh sessions.

After Wayfinder:

```text
/to-spec <cleared-map>
-> user accepts specification
-> /to-tickets <accepted-specification>
```

Continue Wayfinder if decisions remain open. Do not restart the same decision process through `/grill-with-docs`.

Completion condition: the work has either one safe direct implementation route or an accepted multi-session route.

## Step 6: create and approve the specification

`/to-spec` synthesizes the accepted decisions. It does not repeat the entire interview.

Before the specification is accepted, agree on the highest practical test seams. Prefer existing seams and add new seams only when required behavior cannot be tested reliably without them.

The specification records:

- the problem;
- the user-visible solution;
- user stories and acceptance behavior;
- state and authority rules where relevant;
- failure behavior;
- implementation constraints without brittle file-by-file prescriptions;
- testing decisions;
- explicit exclusions;
- the evidence that settled risky questions.

Completion condition: the human accepts the specification, it contains the settled decisions without contradiction, and its required behavior can be divided into implementation tickets.

## Step 7: create implementation tickets

`/to-tickets` converts the accepted specification into narrow vertical slices.

Each ticket must:

- deliver observable behavior through every required layer;
- fit one fresh implementation session;
- declare its blockers;
- use the accepted domain language;
- contain acceptance behavior and required checks;
- avoid reopening settled product decisions;
- be independently demonstrable or verifiable.

The human reviews ticket size, ordering, dependencies, and coverage before implementation begins.

Completion condition: every required behavior belongs to a ticket, the human accepts the breakdown, and at least one unblocked ticket forms the starting frontier.

## Step 8: implement one ready ticket

Start each implementation ticket in a fresh session. Select only a ticket whose blockers are complete.

For the default `implement` route, the Worker must:

1. Read the ticket, specification, domain vocabulary, relevant ADRs, and repository instructions.
2. Confirm the acceptance behavior and test seams.
3. Use `/tdd` for one red and green behavior at a time.
4. Run focused tests and type checking during the change.
5. Run the full required checks and capture evidence of the affected behavior.
6. Create a local candidate commit containing all ticket changes. Record the base and candidate SHAs.
7. Read Matt's `code-review`. Run the existing two internal assignments under the [adapted Matt procedure](../docs/agents/controller-workflow.md#adapted-matt-internal-review) and approved model policy on that committed candidate.
8. Repair valid internal-review blocking findings. Run affected checks, commit a replacement and repeat both independent candidate-bound reviews until both PASS before the first gate verdict. Later gate-requested repairs follow [gate-stage repair review](../docs/agents/controller-workflow.md#gate-stage-repair-review). Internal rounds have no numeric cap. Preserve original report identities/history; the SAME separate gate retains its three-verdict limit.
9. Return the final candidate SHA, acceptance-check results, runtime evidence, and remaining risks to the controller.

The installed `code-review` uses `git diff <fixed-point>...HEAD`; uncommitted changes are excluded. Confirm that `HEAD` is the candidate and that the reviewed diff contains every ticket change. Any later implementation change invalidates approval of the earlier candidate. Keep upstream skill files unchanged; the task packet supplies this project review sequence.

Match verification to the claim: drive the affected UI or CLI, read persisted state, or replay the relevant input and failure case. Label mocks, fixtures, and real integrations. Report unavailable verification as unresolved. Run external operations only within the task's authorized scope.

Preserve unrelated user changes in a dirty worktree. Do not expand a ticket to include unrelated cleanup.

Completion condition: acceptance behavior passes, required checks are green, review blockers are resolved, and the controller accepts the evidence for the exact candidate. The controller records integration and updates ticket state before its dependents become eligible.

## Step 9: verify the complete result

After all implementation tickets are complete:

1. Run the complete user job.
2. Run the full verification suite from a clean setup when practical.
3. Test the main failure cases.
4. Compare the result with the accepted specification.
5. Inspect deployment, migration, documentation, or operational steps affected by the change.
6. Perform an independent review when the risk justifies it.
7. Ask the human to accept the running result.

Completion condition: the complete result satisfies the specification, required evidence is available, and the human accepts the outcome.

## Controller role for multi-session work

Use a controller when work spans several decision or implementation sessions.

The controller:

- records current state and accepted decisions;
- identifies the next unblocked unit of work;
- prepares its exact input list and output requirement;
- audits returned evidence;
- updates dependencies and status;
- keeps unrelated context out of fresh sessions;
- asks the human for decisions that require human judgment.

The controller should not perform a dispatched unit in the same context. This preserves an independent audit boundary.

For implementation, send one task packet containing:

```text
Ticket and approved specification:
Executor skill path and version or source revision:
Selected playbook, when applicable:
Implementation repository, branch, worktree, and base SHA:
Owned files and shared-contract boundaries:
Permitted tools, external operations, and delegation:
Acceptance behavior and agreed TDD seams:
Required checks and runtime evidence:
Review owner, scope, gate counter, external/run limits, and escalation condition:
Actual models, reasoning effort, speed, and approved overrides:
Return format and completion route:
Controller/reply pane and worker/gate destinations:
```

For pane-based work, use the [Smux messaging and standby rules](../docs/agents/controller-workflow.md#messaging-integration-and-handoff). Return results to the recorded recipient pane. After sending, await its incoming message; background thread-status loops are not a substitute. Durable candidate/report records remain the completion evidence.

Parallel writers need disjoint owned surfaces and isolated worktrees. Serialize changes to shared contracts or files. Record who may merge or publish. After integration, verify the combined behavior before recording the ticket as integrated.

Use a durable handoff file with:

```text
Current objective:
Current stage:
Last completed work:
Accepted decisions:
Open blockers:
Artifact ledger:
Active tickets, executor, branch, worktree, and base SHA:
Candidate SHA, review result, and evidence paths:
Integration revision and verification result:
Next action:
Next-session inputs:
Next-session output:
Completion condition:
Recovery instructions:
Last updated:
```

Completion condition: a fresh controller can continue from the recorded next action without reading a full transcript.

## Context and session rules

### Focused planning route

Keep `/grill-with-docs`, returned prototype findings, `/to-spec`, and `/to-tickets` in one context while that context remains reliable. Use a fresh session for each implementation ticket.

### Wayfinder route

- Chart the map in one session.
- Resolve one non-research decision ticket per session.
- Run independent research in parallel when useful.
- Run `/to-spec` in a fresh session after the map clears.
- Use a fresh session for each implementation ticket.

### Choose boundaries deliberately

- Continue when the current context remains necessary and reliable.
- Start fresh when the next work does not need the current conversation.
- Use `/handoff` when work moves to another session, directory, branch, tool, or collaborator.
- Use a background agent for a bounded independent task that can return one artifact.
- Compact when the same work must continue but the context has grown too large.

Write decisions before changing sessions. A new session cannot recover reasoning that was never saved.

## Failure handling

### A session disconnects

Start a replacement session. Read the durable handoff, controlling specification or map, and last completed artifact. Verify external state before repeating any action whose completion is unknown.

### Research conflicts with an accepted decision

Record the conflict. Do not silently rewrite the decision. Reopen it with the human when the new evidence is material.

### Implementation exposes a missing decision

Stop the affected ticket. Record the question and route it to focused grilling, a prototype, or Wayfinder. Resume implementation after the decision enters the specification or an accepted amendment.

### A prototype fails

Return `NARROW` when a smaller useful claim survives. Return `REJECT` when the important claim fails. Do not harden a failed prototype into production code.

### Review finds work outside the ticket

Record a separate issue when the work matters. Keep the current ticket within its accepted boundary.

## Common mistakes

- Starting the workflow before idea selection is complete.
- Using Wayfinder because the codebase is large rather than because the decisions are unclear.
- Running both planning routes over the same questions.
- Treating research as a product decision.
- Treating a prototype as production code.
- Copying prototype architecture into the specification without review.
- Creating implementation tickets before the specification is accepted.
- Splitting tickets by frontend and backend instead of complete behavior.
- Letting an implementation session reopen settled scope without recording the new decision.
- Asking the authoring context to provide the only review.
- Starting a fresh session before writing the current state.
- Copying the same decision into several files instead of linking one source.

## Adoption checklist

Before the first project run:

- [ ] Confirm the required Matt skills are installed.
- [ ] Run or audit repository setup.
- [ ] Record project paths and verification commands.
- [ ] Choose the issue tracker and domain-document layout.
- [ ] Decide whether the starting input has passed idea selection.
- [ ] Choose `/grill-with-docs` or `/wayfinder` based on decision complexity.
- [ ] Name every research or prototype question before starting it.
- [ ] Define who records state across sessions.
- [ ] Define the human approval points.

Before implementation:

- [ ] Resolve every decision that blocks the build.
- [ ] Accept the specification.
- [ ] Accept ticket size and dependencies.
- [ ] Record test seams and required commands.
- [ ] Make the next ready ticket unambiguous.

Before completion:

- [ ] Run the full required checks.
- [ ] Test the complete user job and main failure cases.
- [ ] Resolve blocking review findings.
- [ ] Update affected documentation and operational instructions.
- [ ] Record evidence and the final human decision.

## Minimal starting prompt

Use this after copying the playbook into a repository:

```text
Read `playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md` and the repository's agent instructions.

First audit whether the repository has the tracker, domain-document rules, ADR location, specification location, and verification commands required by Step 0.

Then inspect the proposed starting input. Decide whether it is ready for this engineering workflow or still needs idea selection.

If it is ready, recommend `/grill-with-docs` or `/wayfinder`. Give concrete reasons based on the number, dependency, and uncertainty of the remaining decisions.

Do not begin implementation. Ask the human to approve the route first.
```

## Maintenance

Recheck the installed skills when their version or behavior changes. Update this playbook only when the shared route changes. Keep project-specific decisions in that project's domain documents, ADRs, maps, specifications, tickets, and handoff.
