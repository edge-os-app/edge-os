"""Shared helpers that drive the public API the way the web app does."""

from __future__ import annotations

import copy
import uuid
from typing import Any

THESIS = ("Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. "
          "Spot only.")
HUNCH = "Recent rises seem to keep running. Is that worth testing?"
NO_THESIS = ("I have no view. Look at this market over the last two days and tell me whether anything is worth "
             "testing.")
LAUNCH_AGE = "Tokens launched in the last 24 hours seem to keep running after a rise. Is that worth testing?"
RESTRICTIONS = ["no leverage", "one open position maximum"]
MARKET = {"network": "MONAD", "base_asset": "0x1111111111111111111111111111111111111111",
          "quote_asset": "0x2222222222222222222222222222222222222222"}


def submit(client, headers, text=THESIS, *, job="CREATE_STRATEGY", input_class="CONCRETE_THESIS",
           restrictions=None, declared_market=None):
    body: dict[str, Any] = {"original_request": text, "restrictions": list(RESTRICTIONS if restrictions is None
                                                                            else restrictions),
                            "requested_job": job, "input_class": input_class}
    if declared_market is not None:
        body["declared_market"] = declared_market
    return client.post("/v1/research/requests", json=body, headers=headers)


def answer(client, headers, bundle, question_id, choice_id):
    intake_id = bundle["intake"]["record_id"]
    return client.post(f"/v1/research/requests/{intake_id}/clarifications", headers=headers, json={
        "previous_revision_id": bundle["head"]["interpretation_revision_id"], "question_id": question_id,
        "choice_id": choice_id})


def compiled_thesis(client, headers, **kwargs):
    first = submit(client, headers, **kwargs)
    assert first.status_code == 201, first.text
    bundle = first.json()
    assert bundle["head"]["outcome"] == "NEEDS_CLARIFICATION"
    second = answer(client, headers, bundle, "adopt-suggested-settings", "adopt")
    assert second.status_code == 201, second.text
    bundle = second.json()
    assert bundle["head"]["outcome"] == "COMPILED", bundle["head"]
    return bundle


def publication_body(bundle, *, key=None, parent=None, operation_id=None, strategy=None):
    draft = next(d for d in bundle["drafts"] if d["record_id"] == bundle["head"]["draft_id"])
    return {"operation_id": operation_id or str(uuid.uuid4()), "idempotency_key": key or f"key-{uuid.uuid4()}",
            "expected_parent_revision_id": parent, "draft_id": bundle["head"]["draft_id"],
            "strategy": copy.deepcopy(strategy or draft["content"]["source_syntax"])}


def publish(client, headers, bundle, **kwargs):
    body = publication_body(bundle, **kwargs)
    strategy_id = body["strategy"]["strategy_id"]
    return client.post(f"/v1/strategies/{strategy_id}/revisions", json=body, headers=headers), body
