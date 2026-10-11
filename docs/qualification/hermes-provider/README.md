# Hermes provider qualification package (P05 continuation)

Task P05-QUALIFICATION-PREP-20261011-v1, issue 15. Status: PROPOSED, NOT_RUN.

This folder prepares a later real-model check of the saved Research interpretation path. It is not authority. It makes no live request, reads no credential and spends nothing. No live request is allowed in this task.

| File | What it holds |
|---|---|
| `QUALIFICATION_PROPOSAL.md` | The proposed batch: route, request ceilings, spend arithmetic, pass conditions, stop rules, open decisions. |
| `CASE_MANIFEST.json` | Eleven hand-written cases with expected literals and user quotations. |
| `IDENTITIES.json` | The pinned identities. A test compares it with the code. |
| `HOSTING_ASSESSMENT.md` | What a production host must provide. Names no vendor choice. |
| `LIVE_RELEASE_CHECKLIST.md` | The separate checklist that a controller release must complete before any live request. |

Code that goes with this package lives in `scripts/hermes_interpretation/`: `provider_guard.py`, `spend_ledger.py`, `guarded_turn_runner.py`, `guarded_turn_job.py`, `guarded_docker_runner.py`, `meaning_check.py`, `leak_scan.py` and `qualification_identities.py`. The application does not import any of them. They are test and qualification support only.

Three claims stay separate:

1. **Interpretation quality.** Does a real model keep the user's meaning? NOT_RUN.
2. **Runtime mechanics.** Do the guard, the spend ledger and the saved path behave? Shown locally with controlled responses.
3. **Production feasibility.** Can a host run this safely? Assessed from documents only. NOT_RUN.

Run the new tests from `apps/api`:

```
uv run --frozen pytest -p no:cacheprovider -q tests/provider_safeguards
P05_EVIDENCE_DIR=<private folder> uv run --frozen pytest -p no:cacheprovider -q ../../tests/hermes_interpretation/provider_safeguards
```

The second command needs Docker. It builds the pinned Hermes image, which needs network access for the locked package install only.
