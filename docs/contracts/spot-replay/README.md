# Spot replay result records

This document defines the P13 result record added by the deterministic replay module. It uses the adopted `p12.spot-replay/1` and `p12.essential-evidence/1` contracts without changing P02, P06, P07 or P12 behavior.

## Evidence status

`ReplayDataset.evidence_class` identifies the evidence source. Its default is `SYNTHETIC_FIXTURE`. A P07 `QUALIFIED` label does not change that class or qualify the data for a real market claim. The authored WC-01 fixture has synthetic identities, observations, costs and expected results.

The replay function accepts only a dataset with P07 qualification `QUALIFIED` and complete interval coverage. That admission check does not establish that a real dataset is qualified. This P13 slice has no provider path and cannot promote a fixture or local record to real evidence.

Successor compatibility (R58 L2, 2026-10-14): the runtime also admits `PROVIDER_ACTUAL`. Only the saved-dataset adapter can supply it, and only from a hash-verified owner dataset that an approved actual release collected (source class `PROVIDER_ACTUAL`, saved release kind `ACTUAL`); any other dataset that claims it is refused `evidence_class_inconsistent`. Every other admission rule is unchanged, so the class upgrades no qualification, coverage, market binding or permission. Equal buckets give equal results; the class is part of the repeatability identity. Fills stay hypothetical `simulated fills`, and the saved notice claims no statistical support, profitability or trading permission. Every other class stays `EVIDENCE_CLASS_UNSUPPORTED`. No actual release is approved, so no such dataset exists yet.

## Result contents

The deterministic result contains:

- a SHA-256 repeatability identity over the calculation profile, saved strategy, configuration, dataset, descriptor, window, initial capital and scheduled observations;
- ordered samples, decisions, orders, reservations, fills and completed trades;
- quote-denominated gain/loss, completed entry/exit pairs and absolute quote drawdown;
- a status and reason list for each metric; and
- open base amount, fee-inclusive basis and the last qualified mark with its timestamp and availability.

An unavailable sample does not change known cash or base. Gain/loss and full-period drawdown become unavailable when a required mark is missing. Each unavailable result retains the ordered source reasons. The completed-pair count reports only pairs that did complete during this replay.

## Action timing and saved inputs

The runtime preserves P06 results and reasons, then evaluates action eligibility separately. It checks delivery timing for each primitive observation consumed by the full entry or exit expression, including both sides of a Boolean expression and the operands of supported history operators. A decisive sibling cannot hide a future observation or a value whose delivery time is unknown. Such a field is ineligible for that decision, while its original P06 truth value and reasons remain unchanged. P06 reasons that arise from missing or operation-unused inputs are not blanket filters; the adopted WC-06 and WC-14 cases remain distinct. The separately declared P12 essential dependencies remain an additional, independent eligibility check.

Retrieved runs display the exact immutable input snapshot returned by the API. In particular, the saved bindings are not reconstructed from current editor values. A definitive HTTP 422 input rejection is safe to correct and submit as a new attempt. For an uncertain outcome, the original idempotency key and body remain paired; edits do not change the retry payload.

## Version boundary

`p12.spot-replay/1` and `p12.essential-evidence/1` remain exact adopted inputs. Their saved identities and terms are not rewritten by this result record. A future result schema change requires a new version and an explicit migration or compatibility rule. This document does not grant trading permission or qualify data, fills or costs.
