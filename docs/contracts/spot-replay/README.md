# Spot replay result records

This document defines the P13 result record added by the deterministic replay module. It uses the adopted `p12.spot-replay/1` and `p12.essential-evidence/1` contracts without changing P02, P06, P07 or P12 behavior.

## Evidence status

`ReplayDataset.evidence_class` identifies the evidence source. Its default is `SYNTHETIC_FIXTURE`. A P07 `QUALIFIED` label does not change that class or qualify the data for a real market claim. The authored WC-01 fixture has synthetic identities, observations, costs and expected results.

The replay function accepts only a dataset with P07 qualification `QUALIFIED` and complete interval coverage. That admission check does not establish that a real dataset is qualified. This P13 slice has no provider path and cannot promote a fixture or local record to real evidence.

## Result contents

The deterministic result contains:

- a SHA-256 repeatability identity over the calculation profile, saved strategy, configuration, dataset, descriptor, window, initial capital and scheduled observations;
- ordered samples, decisions, orders, reservations, fills and completed trades;
- quote-denominated gain/loss, completed entry/exit pairs and absolute quote drawdown;
- a status and reason list for each metric; and
- open base amount, fee-inclusive basis and the last qualified mark with its timestamp and availability.

An unavailable sample does not change known cash or base. Gain/loss and full-period drawdown become unavailable when a required mark is missing. Each unavailable result retains the ordered source reasons. The completed-pair count reports only pairs that did complete during this replay.

## Version boundary

`p12.spot-replay/1` and `p12.essential-evidence/1` remain exact adopted inputs. Their saved identities and terms are not rewritten by this result record. A future result schema change requires a new version and an explicit migration or compatibility rule. This document does not grant trading permission or qualify data, fills or costs.
