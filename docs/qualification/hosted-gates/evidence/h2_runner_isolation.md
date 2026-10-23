# H2 qualified isolated runner (HOST_QUALIFICATION_RUNBOOK §5.4, §5.7)

Status: **NOT RUN**. The controller runs these checks on the VPS and records the output. This file is a template; no
check below ran for this file.

Operator: `<name>`. Date: `<UTC>`. Host: VPS `vmi3674409`.

## Exact checks from the runbook

Runbook row 5.4, Hermes whole-process isolation:

> The accepted LOCAL helper `dbd95668` runs pinned Hermes in a no-network, read-only job container (512 MB, 1 CPU,
> 64 processes, no capabilities, no socket, no host workspace) and refuses the actual route. The credential file is
> mounted read-only, but the job, transport and Hermes share one process, so the credential copy is readable by Hermes
> code; credential isolation needs a separately decided host-held relay. **The public API/model process must not mount
> the host Docker socket.**

Runbook row 5.7, trusted runner boundary:

> The accepted LOCAL helper `dbd95668` provides the runner (`build_transport_job`, `TransportJob.runner`,
> `recover_pending(C)`), but it is not mounted and the durable shared ledger and host supervisor remain proposals. A
> helper present in a plan is not an accepted runner.

## Results

Record the actual container inspection and job output. Do not label a hosted H2 check PASS when it only ran in a local
fixture or only appears in a plan.

| # | Check | Expected observation | Result |
|---|---|---|---|
| 1 | Job container isolation | pinned Hermes runs in a no-network, read-only job container | NOT RUN |
| 2 | Resource bounds | 512 MB memory, 1 CPU, 64 processes | NOT RUN |
| 3 | Capability and socket bounds | no added capabilities, no Docker socket, no host workspace | NOT RUN |
| 4 | Actual route refusal | the actual provider route is refused | NOT RUN |
| 5 | Credential mount | credential file is mounted read-only | NOT RUN |
| 6 | Credential isolation | the job, transport and Hermes share one process, so Hermes code can read the credential copy; a host-held relay is required and not yet decided | NOT RUN |
| 7 | API/model process | the public API and model process do not mount the host Docker socket | NOT RUN |
| 8 | Runner presence | `build_transport_job`, `TransportJob.runner` and `recover_pending(C)` are mounted and reachable | NOT RUN |
| 9 | Owned supervision | a durable shared ledger and a host supervisor are accepted, not proposals | NOT RUN |
| 10 | Cleanup | a completed, cancelled and timed-out job cleans its process and temporary files | NOT RUN |

## Stop condition

A missing isolation control keeps real-model and hosted research unavailable. Do not run a real Hermes job without the
accepted isolation and a recorded inference budget.

## Recorded evidence

Operator fills: the container inspect output, the job log, the date, and any deviation.
