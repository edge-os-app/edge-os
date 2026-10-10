# Internal reviewer packet

Fill this once for A and once for B, and launch separate contexts. These are the existing pair, not extra reviews. Follow [adapted Matt review](../controller-workflow.md#adapted-matt-internal-review), [original reports](../controller-workflow.md#original-reviewer-reports) and [model policy](../../../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md#approved-model-policy).

```text
You are independent internal reviewer <A or B> for <task/issue>.
Packet identity/version and assignment authority: <filled>.
Execution profile/version and return transport: <filled>.
Assigned host/model/effort: <explicit configured selection; unavailable serving telemetry is non-blocking>.
Prompt profile/source date: <matched to observed host/model>.
Repository/checkout: <actual absolute path>. Base SHA: <exact>. Candidate SHA: <exact>.
Accepted issue/specification/ADRs/profile: <repository paths or issue attachments and versions>.
Required prior findings/examples: <portable inputs, exact sections and retained limits>.
Owned review scope and forbidden mutations: <filled>; review is read-only.
Required skills: <names, actual instruction paths, applicability reasons and references>.
Read AGENTS.md and selected instructions before use. Apply General Review Protocol, then Review Verification Protocol, Code Reviewer and Code Review Excellence, plus the assigned domain skills.
Use the worker's Matt code-review checklists under the project adaptation; do not launch another reviewer pair.
A's primary scope: accepted specification, correctness, scope, tests and integration.
B's primary scope: repository standards and maintainability, assumptions, failures, permissions, recovery and relevant numerical/statistical validity.
Either reviewer may report a verified defect outside its primary scope.
Keep the other reviewer's initial findings hidden. Do not use the implementer's conclusions as your own assessment.
Required own checks: <commands and expected behavior>.
Worker evidence to inspect: <exact reports, candidate/configuration/input identities>.
Verification cadence: controller-workflow.md#verification-cadence; distinguish own execution from inspected evidence. Do not invent broad application tests for a documentation-only assignment.
Verify ancestry and the complete base-to-candidate scope; preserve the candidate and other writers' files. Use isolated resources if assigned checks write outputs.
Verify suspected defects against accepted requirements, actual surrounding behavior and callers. Reproduce when possible. State consequence and file/line evidence. Preferences alone are not blockers; preserve Ponytail Lite completeness and safety.
Outside-scope upstream defects: follow controller-workflow.md#upstream-defects-found-downstream; report rather than edit.
Save your original assessment to <report path>. Include task/context identity, exact base/candidate, selected model, skills actually used, own checks/results, evidence inspected, verified findings, unavailable checks and explicit PASS or REVISE.
Return to <assignment owner/native parent/assigned PR>; follow the recorded transport. For Smux, send the frozen path/hash pointer with checked Enter/submission; other routes mark pane fields inapplicable.
Internal round/history: <filled; uncapped>. Gate counter: <unchanged; internal rounds do not consume it>.
This review approves only its exact candidate and grants no source edits, publication, merge, provider or financial authority.
```

For a replacement assessment, identify the previous candidate, repair range, prior findings and affected unchanged invariants. Initial internal repairs and sensitive/broad gate repairs require both candidate-bound reviews. A controller-authorized narrow gate repair may return directly to the same gate under [the canonical rule](../controller-workflow.md#gate-stage-repair-review); do not invent a replacement pair for that route.
