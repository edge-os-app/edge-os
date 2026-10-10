# Domain documentation

Use a single-context layout:

- `CONTEXT.md` for settled domain vocabulary.
- `docs/adr/` for accepted architecture decisions.

Before exploring a task, read the context document and relevant ADRs if they exist.

If these documents do not exist, proceed. Domain modeling creates them as terms and decisions become settled.

Use the glossary's defined terms. Record missing concepts for domain modeling instead of silently introducing conflicting names.

Surface conflicts with accepted ADRs before changing the affected behavior.

Keep recommendations separate from accepted decisions. An ADR must identify its approval status and supporting evidence.

## Shared documents and private evidence

The repository is authoritative for the Edge OS specification, research contracts, scoped probe plan, project workflow and implementation configuration. Change those documents here. Workspace copies are redirects, not independently editable specifications.

The repository handoff records team-facing state. The builder keeps detailed controller history and research archives outside this repository. Reusable playbooks outside the repository are templates; changes to them do not automatically change this project's rules.

`BUILDER-ONLY REFERENCE` identifies source material kept in the builder's private workspace and excluded from a teammate's clone. Its path is relative to that private workspace, not this repository. Preserve the source name and any section or line locator for provenance. A reference label is not new evidence or an instruction to read outside the checkout.

On the builder's host, [read-only prior-project discovery](controller-workflow.md#read-only-prior-project-discovery) separately permits task-relevant searches in the explicitly authorized local reference roots. Use the [implementation reference map](../research/EDGE_OS_IMPLEMENTATION_REFERENCE_MAP.md) for published context. This optional permission does not replace the portable required-input rule below.

For an implementation task that depends on private evidence, the builder must supply the necessary verified extract, semantics, fixtures, source/version identifiers and limitations in the issue or a repository artifact. If they are missing, report the exact missing input and pause the affected work. Do not invent behavior or silently weaken an acceptance check.

The copied hackathon brief is a published research snapshot. Official current rules control contest facts. Any refreshed builder research must be explicitly incorporated into the repository snapshot; do not maintain two independently researched briefs.
