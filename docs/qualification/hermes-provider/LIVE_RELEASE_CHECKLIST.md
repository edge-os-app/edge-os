# Live release checklist for Hermes interpretation

Status: a blank checklist. NOT_RUN. This file is not authority. It makes no live request. A controller must complete and record every line before any provider request, and the builder's separate permission must cover the spend. Local passing tests complete none of these lines.

| # | Line | Needs |
|---|---|---|
| 1 | Provider, model, route, reasoning level named | Controller record |
| 2 | Current prices read from the provider's public price list, with date and URL; reservations recomputed | Fresh `IDENTITIES.json` section `reservations` |
| 3 | Pinned identities equal the code at the release commit (prompt, shape, Hermes, lock, manifest, support files) | `qualification_identities.py` output equals `IDENTITIES.json` |
| 4 | Cumulative cap and retry slots set | Controller record |
| 5 | Provider-side ceiling: dedicated limited key, or prepaid balance, or a written acceptance of local accounting only | Person sets it. A controller verifies it read-only. |
| 6 | Credential route: where the secret lives, who injects it, how it reaches the job as a file | Controller record. No value in any prompt, record or log. |
| 7 | Egress policy for the job (provider host only) and how it was checked | Not established by current documents |
| 8 | Live job entrypoint written, reviewed and tested locally with controlled responses | Separate ticket |
| 9 | Spend ledger on durable shared storage with the same rules | Separate ticket |
| 10 | Deadline and kill path; evidence folder created; separate labels for controlled, real-provider and participant evidence | Controller record |
| 11 | Stop rules from the proposal copied into the run instruction | Proposal section 8 |
| 12 | The batch is the 11 manifest cases, one request each, no automatic retry | `CASE_MANIFEST.json` |
| 13 | Rollback: live setting off, key revoked or limited, ledger kept | Controller record |
| 14 | Owner of each step and the reply pane | Controller record |
| 15 | The live job always gives the guard the injected credential (`credential=None` is for local runs only) | Live job review |
| 16 | A recorded decision path exists to resolve an UNKNOWN reservation without late evidence, before any retry slot is used | Separate ticket |

Do not run any step of this list from the Hermes tests. The tests use dummy credentials only.
