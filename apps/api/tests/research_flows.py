"""Helpers that drive the #58 recorded-history research API the way the web app does.

Every source here is a SYNTHETIC recorded-response bundle (`history_recordings.py`). Nothing reaches a provider.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from flows import NO_THESIS, submit

QUALIFIED = "recorded-syn-qualified/1"
QUOTE_UNIT = "QUOTE:0x" + "bb" * 20
REVIEW = "history-investigation-review/1"
FIELDS = ("edge_spec", "question", "source", "market", "window", "variants", "direction", "horizons", "partitions",
          "evaluation_plan", "schedule", "rule_map", "resource_bounds", "permitted_access", "stopping_rule",
          "budget_version")


def rising(lookback: int = 1) -> dict[str, Any]:
    """The newest delivered bucket's price return over `lookback` buckets is positive."""
    return {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": lookback},
                                 {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}


def volume_above(value: str, unit: str = QUOTE_UNIT) -> dict[str, Any]:
    return {"op": "gt", "args": [{"op": "quote_volume"}, {"op": "constant", "value": value, "unit": unit}]}


def source_entry(client, headers, source_id: str = QUALIFIED) -> dict[str, Any]:
    sources = client.get("/v1/research/history-sources", headers=headers).json()["sources"]
    return next(item for item in sources if item["source_id"] == source_id)


def history_body(client, headers, bundle, *, source_id: str = QUALIFIED, key: str | None = None,
                 direction: str = "OUTPERFORM", rules: list[tuple[dict[str, Any], dict[str, Any]]] | None = None,
                 bounds: dict[str, int] | None = None, partition: str | None = None) -> dict[str, Any]:
    source = source_entry(client, headers, source_id)
    window = source["window"]
    trial = str(uuid.uuid4())
    unit = f"QUOTE:{source['market']['quote_asset']}"
    rules = rules or [(rising(1), volume_above("101", unit)), (rising(2), volume_above("102", unit))]
    evaluations = [str(uuid.uuid4()) for _ in rules]
    variants = [f"v{index + 1}" for index in range(len(rules))]
    descriptive = direction == "DESCRIPTIVE"
    if descriptive:
        partitions = [{"partition_id": "described", "role": "DESCRIPTIVE", "start": window["start"],
                       "end": window["end"]}]
    else:
        partitions = [
            {"partition_id": "train", "role": "TRAINING", "start": window["start"], "end": "2026-09-25T11:00:00Z"},
            {"partition_id": "validate", "role": "VALIDATION", "start": "2026-09-25T11:00:00Z",
             "end": "2026-09-25T11:30:00Z"},
            {"partition_id": "holdout", "role": "HOLDOUT", "start": "2026-09-25T11:30:00Z", "end": window["end"]},
        ]
    first_partition = partition or partitions[0]["partition_id"]
    return {
        "operation_id": str(uuid.uuid4()), "idempotency_key": key or f"rg01-{uuid.uuid4()}",
        "expected_interpretation_revision_id": bundle["head"]["interpretation_revision_id"],
        "edge_spec": {
            "edge_id": str(uuid.uuid4()), "version": 1, "parent_declaration_id": None,
            "hypothesis": "After a rising five-minute bucket, the next bucket keeps rising on this pool.",
            "claim": {"status": "DESCRIPTIVE_ONLY" if descriptive else "HYPOTHESIS",
                      "text": "Describe only." if descriptive else "Triggered decisions outperform untriggered ones."},
            "falsification": {"status": "DESCRIPTIVE_ONLY" if descriptive else "DECLARED",
                              "criteria": "No outcome claim." if descriptive else
                              "The triggered minus control mean is not positive."},
            "alternatives": ["Short-term noise explains any difference."],
            "unknowns": ["Recorded responses are synthetic; no real pool behaviour is measured."],
        },
        "configuration": {
            "question": bundle["intake"]["content"]["original_request"],
            "source": {"source_id": source["source_id"], "profile_sha256": source["profile_sha256"],
                       "evidence_class": source["evidence_class"]},
            "market": copy.deepcopy(source["market"]),
            "window": dict(window),
            "variants": [{"variant_id": name, "hypothesis": f"Adopted rule {name}"} for name in variants],
            "direction": "DESCRIPTIVE" if descriptive else direction,
            "horizons": [{"value": 5, "unit": "MINUTES"}],
            "partitions": partitions,
            "evaluation_plan": [{"evaluation_id": evaluation, "trial_id": trial, "variant_id": variant,
                                 "horizon": {"value": 5, "unit": "MINUTES"}, "partition_ids": [first_partition]}
                                for evaluation, variant in zip(evaluations, variants)],
            "schedule": {"version": "p09.decision-clock/1", "start": "2026-09-25T10:15:00Z",
                         "end": "2026-09-25T11:50:00Z", "interval_seconds": 300},
            "rule_map": {"schema_version": "edge-os.hypothesis-rule-map/1", "control": "UNTRIGGERED_DECISIONS",
                         "incremental_volume_declared": True,
                         "rules": [{"evaluation_id": evaluation, "trial_id": trial, "variant_id": variant,
                                    "price_expression": price, "volume_expression": volume,
                                    "essential_inputs": ["price", "quote_volume"], "rule_source": "USER_ADOPTED"}
                                   for evaluation, variant, (price, volume) in zip(evaluations, variants, rules)]},
            "resource_bounds": bounds or {"provider_requests": (source["transport"] or {}).get(
                                              "provider_requests_needed", 2), "compute_seconds": 30, "max_pages": 2,
                                          "max_rows": 200, "max_bytes": 1_048_576, "deadline_seconds": 600},
            "permitted_access": [source["evidence_class"]],
            "stopping_rule": "Stop after the declared evaluations on the declared window.",
            "budget_version": "edge-os.research-budget/1",
        },
        "field_origins": {name: {"origin": "USER_STATED" if name == "question" else "USER_CONFIRMED",
                                 "source_ref": "original_request" if name == "question" else REVIEW,
                                 "adoption": "ADOPTED"} for name in FIELDS},
        "trial_ids": [trial],
        "evaluation_ids": evaluations,
    }


def investigation_request(client, headers) -> dict[str, Any]:
    response = submit(client, headers, NO_THESIS, job="INVESTIGATE_EFFECT", input_class="BOUNDED_NO_THESIS")
    assert response.status_code == 201, response.text
    return response.json()


def declare(client, headers, **kwargs) -> tuple[str, str, dict[str, Any]]:
    bundle = investigation_request(client, headers)
    intake_id = bundle["intake"]["record_id"]
    body = history_body(client, headers, bundle, **kwargs)
    saved = client.post(f"/v1/research/requests/{intake_id}/history-investigations", headers=headers, json=body)
    assert saved.status_code == 201, saved.text
    return intake_id, saved.json()["declaration"]["record_id"], body


def jobs_path(intake_id: str, declaration_id: str) -> str:
    return f"/v1/research/requests/{intake_id}/history-investigations/{declaration_id}/jobs"


def start(client, headers, intake_id: str, declaration_id: str, key: str | None = None, operation_id: str | None = None):
    return client.post(jobs_path(intake_id, declaration_id), headers=headers,
                       json={"operation_id": operation_id or str(uuid.uuid4()),
                             "request_key": key or f"job-{uuid.uuid4()}"})


def reported_dataset(client, headers, source_id: str = QUALIFIED, direction: str = "OUTPERFORM",
                     rules: list[tuple[dict[str, Any], dict[str, Any]]] | None = None) -> str:
    """Declare, run one job to its report with a local worker, and return the saved dataset id."""
    from edge_os_api.research.investigation_jobs import InvestigationWorker

    intake_id, declaration_id, _ = declare(client, headers, source_id=source_id, direction=direction, rules=rules)
    job_id = start(client, headers, intake_id, declaration_id).json()["job_id"]
    InvestigationWorker(client.app.state.session_factory, client.app.state.settings).run_job(uuid.UUID(job_id))
    view = client.get(f"/v1/research/investigation-jobs/{job_id}", headers=headers).json()
    assert view["state"] == "REPORTED", view["state"]
    dataset_id = view["dataset"]["dataset_id"]
    DECLARED_RULES[dataset_id] = view["report"]["content"]["rule_map"]["rules"][0]["evaluation_id"]
    return dataset_id


# The user's own exit, restated at adoption: the two-bucket return falls below -0.1%. Not a worked-example rule.
OWN_EXIT = {"op": "lt", "args": [{"op": "price_return", "lookback_buckets": 2},
                                 {"op": "constant", "value": "-0.001", "unit": "DIMENSIONLESS"}]}


def first_declared_rule(client, headers, dataset_id: str) -> str:
    datasets = client.get("/v1/research/history-datasets", headers=headers).json()["datasets"]
    return next(item for item in datasets if item["dataset_id"] == dataset_id)["declared_rules"][0]["evaluation_id"]


# dataset id -> the first rule its declaration adopted, filled by `reported_dataset`.
DECLARED_RULES: dict[str, str] = {}
UNKNOWN_RULE = "00000000-0000-4000-8000-000000000001"


def adoption_body(bundle, dataset_id: str, *, evaluation_id: str | None = None, parent: str | None = None, key: str | None = None,
                  quote_unit: str = QUOTE_UNIT, amount: str = "50", notional: str = "50",
                  exit_rule: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"idempotency_key": key or f"market-{uuid.uuid4()}",
            "evaluation_id": evaluation_id or DECLARED_RULES.get(dataset_id, UNKNOWN_RULE),
            "exit_rule": copy.deepcopy(exit_rule or OWN_EXIT),
            "expected_interpretation_revision_id": bundle["head"]["interpretation_revision_id"],
            "expected_parent_revision_id": parent, "dataset_id": dataset_id, "adoption": "ADOPT_DATASET_MARKET",
            "quote_unit": quote_unit, "sizing_amount": amount, "max_quote_notional": notional}


def history_replay_body(strategy_id: str, revision_id: str, dataset_id: str, *, start: str = "2026-09-25T10:20:00Z",
                        end: str = "2026-09-25T11:00:00Z", key: str | None = None) -> dict[str, Any]:
    return {"idempotency_key": key or f"replay-{uuid.uuid4()}", "strategy_id": strategy_id,
            "strategy_revision_id": revision_id, "history_dataset_id": dataset_id,
            "run_configuration_id": f"history-{uuid.uuid4()}", "window_start": start, "window_end": end,
            "initial_cash_quote": "1000", "initial_base_amount": "0", "initial_basis_quote": "0",
            "essential_fields": {
                "entry": {"state": "BOUND", "essential_dependencies": [
                    {"series": "price", "offset_buckets": 0}, {"series": "price", "offset_buckets": -1},
                    {"series": "quote_volume", "offset_buckets": 0}]},
                "exit": {"state": "BOUND", "essential_dependencies": [{"series": "price", "offset_buckets": 0},
                                                                     {"series": "price", "offset_buckets": -2}]}}}
