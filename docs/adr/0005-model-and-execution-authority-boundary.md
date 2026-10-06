---
status: accepted
---

# Models propose; the execution service authorizes

The accepted [readiness and permission boundary](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-claim-specific-support-and-readiness-gates) requires deterministic admission and independent wallet checks, as recorded in [ADR 0002](0002-separate-evidence-and-financial-authority.md). Under the specification's [model roles](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#model-and-research-roles) and [execution host](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#execution-host), model agents propose typed records without signing credentials, direct transaction submission or authority to override limits; this permits model assistance while keeping a model answer insufficient to spend.

This records the core boundary only. Credential isolation, policy-administrator separation and actual provider enforcement remain unqualified; exact transport, service topology and any new inventory approver architecture are not approved by this ADR.
