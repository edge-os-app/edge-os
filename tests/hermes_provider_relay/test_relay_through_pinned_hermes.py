"""ACTUAL pinned Hermes (commit 54bc5e5) in a no-network job; its one request leaves only through the relay.

The relay runs in its own container on an internal Docker network shared only with the AUTHORED provider, and is the
only holder of the synthetic key. Each test runs the saved interpretation path (`HermesInterpreter`) over
`build_relay_job` and checks the job report against the relay's records and the provider's receipts. Needs Docker.
"""

from __future__ import annotations

import json

from edge_os_api.research.hermes_interpreter import Interpreted
from leak_scan import find_leaks
from relay_harness import EXACT_CHARGE, RELEASE, ROUTE, Rig, case, counts, provider_receipts, relay_record

from conftest import SENTINEL


def test_one_admitted_request_leaves_through_the_relay_with_the_relay_key_and_is_charged_exactly(
        relay, pinned_hermes_image, evidence_root) -> None:
    rig = Rig(relay, pinned_hermes_image, evidence_root, "valid", case())

    result = rig.run_case()

    assert isinstance(result, Interpreted) and result.attempt_id == "valid-1"
    saved, container = rig.saved(), rig.container_result("valid-1")
    observed = saved.settlement.runtime_observed
    assert (observed["transport_attempt_id"], observed["transport_request_attempt_ids"]) == ("valid-1", ["valid-1"])
    assert (observed["relay_release_id"], observed["relay_started"], observed["relay_outcome"]) == (
        RELEASE.release_id, True, "reply")
    assert observed["spend_state"] == "SETTLED" and rig.spend.committed_usd() == EXACT_CHARGE
    assert saved.settlement.request_count == 1 and counts(relay, "valid-1") == (1, 1)
    [receipt] = provider_receipts(relay, "valid-1")
    assert receipt["bearer_matches"] is True and receipt["path"] == "/v1/chat/completions"
    assert "authorization" in receipt["header_names"] and not {"x-stainless-retry-count", "user-agent"} & set(
        receipt["header_names"])  # nothing of Hermes' own headers passes
    assert container["sandbox"]["network"]["blocked"] is True and container["sandbox"]["credential_mounted"] is False
    assert container["transport"]["credential_attached"] is False
    assert relay_record(relay, "valid-1", "closed")["started"] is True
    assert relay_record(relay, "valid-1", "finished")["usage"] == {"prompt_tokens": 1423, "completion_tokens": 611,
                                                                    "total_tokens": 2034}
    assert ROUTE.route_id == json.loads((relay.path("grants") / "valid-1.json").read_text())["route_id"]
    assert find_leaks(evidence_root / "jobs", SENTINEL) == []
