# P04 repair round 1 final verification

Canonical actual-Hermes run: `qualification-result.json` in this directory. It was executed after the final provider-receipt ownership checks changed from substring matching to exact parsed task snapshots.

- Four actual-Hermes normal tasks covered owner A agents A/B/C and owner B agent D. Corrected owner A/agent A memory and cleared owner A/agent C memory were both version 2. Agent C's actual request carried empty memory and source arrays; the probe completed without an indexing failure.
- The same-owner agent snapshots carried distinct source IDs, file IDs, memory entries, input mounts and cache/HOME paths. All request receipts showed exact expected task snapshots, and forbidden owner/agent source, file and memory values were absent.
- Owner B/agent D's MEM-Q04 fixture note was present in its actual-Hermes fake-provider request. The selected tool count remained zero, the request token maximum remained 128, and the authoritative local control fixture was not mounted and had an unchanged SHA256. This is structural fixture evidence, not a real-model resistance test.
- The two length-output cases recorded actual pinned Hermes calls requesting 256 tokens for `truncation_continuation` and `iteration_summary`. Each had one admitted 128-token local fake-provider work item, one rejected continuation/summary with `provider_work_performed=false`, and `TRUNCATED_PARTIAL`/failed classification. The invalid partial output did not pass P02 validation.
- The healthy image tag was removed and inspected absent; no labeled containers remained. Cancellation recovery remained `INTERRUPTED`/`UNKNOWN`, retained its USD 2.00 local reservation and refused replay.
- Final run IDs before this exact-context regression pass are retained: `p04-692b388e5d0c` and `p04-60b7244fc4dc` also passed the actual runtime, but `p04-b7a0f3a179b9` is canonical for the committed candidate.
- RED/GREEN test checkpoints and injected startup fault results are summarized in the earlier retained `evidence/p04-60b7244fc4dc/repair-r1-tdd.md`; those artifacts remain part of the same candidate evidence tree.

No live inference, key/account change, dashboard change, wallet/API/web action, merge or publication occurred. Production authentication/storage, deployed isolation, Hermes streaming, real-provider behavior/billing, upstream cancellation and real-model interpretation of the malicious note remain unqualified.
