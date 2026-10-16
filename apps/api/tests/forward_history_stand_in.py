"""A SYNTHETIC four-bucket stand-in source with a frozen forward-history handoff (SAVED-HISTORY-BINDING-L2).

Used by the payload-binding tests and the mapped release journey. The source is derived from the SOURCE-LOCAL native
recording `native-syn-qualified/1`: its window is cut to the recorder's 20 minutes (four 300-second buckets) and its scan
to `[B_PRE, B_POST + 1) = [500, 506)`, served by one page. The handoff is authored from that recording's own page with
the accepted checker's projection (`history_payload_binding.checker()`); canonicalization is never copied here.

Everything is SYNTHETIC and local: the handoff is not provider, chain or delivery evidence, and the release is a
`STAND_IN` release over `.invalid` or loopback hosts. `handoff(**changes)` builds deliberately contradicted handoffs for
the failure tests.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import operating_release_stand_in as stand_in
from edge_os_api.core.research.operating_release import BINDING_FACT, HistoryRelease, OperatingRelease
from edge_os_api.core.research.released_source_runtime import (
    NansenHttpFactory,
    ReleasedSourceRuntime,
    open_released_runtime,
)
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research import history_payload_binding
from edge_os_api.research_history.http_clients import StdlibHttpTransport
from edge_os_api.research_history.qualification_engine import epoch, iso_utc

SOURCE_ID = "release-forward-bound/1"
PROFILE_ID = "native-syn-forward-bound/1"
RELEASE_ID = "stand-in-bound/1"
WINDOW_START, WINDOW_END = "2026-09-25T10:00:00Z", "2026-09-25T10:20:00Z"
SCAN = {"from_block": 500, "to_block_exclusive": 506}
B_POST = 505
BUCKET_SECONDS = 300


def _number(value: Any) -> int:
    return int(value, 16) if isinstance(value, str) else int(value)


def recording() -> dict[str, Any]:
    """The four-bucket recording: one page of blocks 500..505, its five Swap logs and their five receipts."""
    source = copy.deepcopy(stand_in.recording())
    page = source["envio_pages"][0]
    blocks = [block for block in page["data"]["blocks"] if _number(block["number"]) <= B_POST]
    logs = [log for log in page["data"]["logs"] if log["block_number"] <= B_POST]
    last = blocks[-1]
    source["envio_pages"] = [{**page, "data": {"blocks": blocks, "logs": logs},
                              "next_block": hex(SCAN["to_block_exclusive"]),
                              "rollback_guard": {"block_number": B_POST, "first_block_number": SCAN["from_block"],
                                                 "hash": last["hash"], "timestamp": last["timestamp"]}}]
    source["scan"] = dict(SCAN)
    source["corroboration_sample_size"] = len(logs)
    profile = source["profile"]
    profile["profile_id"] = PROFILE_ID
    profile["dataset"]["window"] = {"start_utc": WINDOW_START, "end_utc": WINDOW_END}
    facts = source["provider_facts"]
    facts["delivery_records"] = {start: delivered for start, delivered in facts["delivery_records"].items()
                                 if start < WINDOW_END}
    claim = facts["feasibility_claim"]
    claim["partitions"] = [{**claim["partitions"][0], "end_utc": iso_utc(epoch(WINDOW_END) - BUCKET_SECONDS)}]
    source["source_id"] = PROFILE_ID
    source["title"] = "Four-bucket native recording for payload binding (synthetic)"
    return source


def provider_requests(source: Mapping[str, Any] | None = None) -> int:
    """Calls one full collection makes: the pages, one chain read and one receipt per sampled swap."""
    source = recording() if source is None else source
    return len(source["envio_pages"]) + 1 + int(source["corroboration_sample_size"])


def handoff(source: Mapping[str, Any] | None = None, **changes: Any) -> dict[str, Any]:
    """The SYNTHETIC recorder handoff for the recording, in the accepted `edge-os.forward-history-handoff/1` shape.

    Every bucket is delivered at its end (the recording's delivery records), so `available_at` equals the bucket end.
    Counts and digests come from the checker's own projection of the page's logs. Top-level `changes` replace keys."""
    checker = history_payload_binding.checker()
    source = recording() if source is None else source
    page = source["envio_pages"][0]
    headers = {_number(block["number"]): (checker.quantity(block["timestamp"], "timestamp"),
                                          checker.hex_value(block["hash"], 32, "hash"))
               for block in page["data"]["blocks"] if block.get("hash")}
    projected = [checker.project_log(log, block_timestamp=headers[log["block_number"]][0])
                 for log in page["data"]["logs"]]
    profile = source["profile"]
    tokens = {token["role"]: token["address"] for token in profile["pool_tokens"]}
    token0, token1 = sorted((tokens["BASE"], tokens["QUOTE"]))
    delivered = source["provider_facts"]["delivery_records"]
    buckets = []
    for index in range(checker.BUCKET_COUNT):
        start = epoch(WINDOW_START) + index * BUCKET_SECONDS
        members = checker.bucket_members(projected, start, start + BUCKET_SECONDS)
        buckets.append({"index": index, "start_utc": iso_utc(start), "end_utc": iso_utc(start + BUCKET_SECONDS),
                        "status": "DELIVERED", "reply_id": "P3-stand-in-first", "received_at_utc":
                        delivered[iso_utc(start)], "received_at_utc_us": epoch(delivered[iso_utc(start)]) * 1_000_000,
                        "record_count": len(members), "payload_sha256": checker.payload_sha256(members),
                        "reply_body_sha256": None, "reason": None})
    body = {"schema_version": checker.HANDOFF_SCHEMA, "canonicalization_version": checker.CANONICALIZATION_VERSION,
            "attempt_id": "stand-in-forward-attempt-1", "source_id": SOURCE_ID, "evidence_class": "SYNTHETIC",
            "requested_evidence_class": "SYNTHETIC", "status": "COMPLETE",
            "network": {"chain_id": profile["network"]["chain_id"]},
            "market": {"pool": profile["venue"]["pool_address"], "token0": token0, "token1": token1,
                       "base": tokens["BASE"], "quote": tokens["QUOTE"]},
            "window": {"start_utc": WINDOW_START, "end_utc": WINDOW_END, "bucket_seconds": BUCKET_SECONDS},
            "scan": dict(source["scan"]), "scan_log_count": len(projected),
            "headers": [{"number": number, "timestamp": timestamp, "hash": block_hash}
                        for number, (timestamp, block_hash) in sorted(headers.items())],
            "buckets": buckets,
            "delivery_records": {bucket["start_utc"]: bucket["received_at_utc"] for bucket in buckets},
            "notice": "Synthetic stand-in handoff authored from a local recording. Not provider or delivery evidence."}
    body.update(changes)
    return body


def handoff_text(body: Mapping[str, Any]) -> str:
    return record_contract.canonical_bytes(dict(body)).decode("utf-8")


def definition(body: Mapping[str, Any] | None = None) -> dict[str, str]:
    """The release's `forward_history_binding` value for a handoff (the default one when None)."""
    text = handoff_text(handoff() if body is None else body)
    return {"handoff_json": text, "handoff_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def bound_release(*, release_id: str = RELEASE_ID, kind: str = "STAND_IN",
                  envio_endpoint: str = stand_in.INVALID_ENVIO, quicknode_host: str = stand_in.INVALID_QUICKNODE_HOST,
                  nansen: bool = True, nansen_endpoint: str = "https://nansen.stand-in.invalid",
                  binding: Any = "DEFAULT", source_id: str = SOURCE_ID) -> OperatingRelease:
    """A release over the four-bucket recording. `binding=None` leaves it unbound; any other value is set as is."""
    source = recording()
    facts = dict(source["provider_facts"])
    if binding is not None:
        facts[BINDING_FACT] = definition() if binding == "DEFAULT" else binding
    part = HistoryRelease(
        source_id=source_id, title="Stand-in release over the four-bucket bound recording (not provider data)",
        envio_endpoint=envio_endpoint, envio_credential_slot=stand_in.ENVIO_SLOT, quicknode_host=quicknode_host,
        quicknode_credential_slot=stand_in.QUICKNODE_SLOT, profile=source["profile"], scan=source["scan"],
        corroboration_sample_size=int(source["corroboration_sample_size"]), provider_facts=facts,
        limits=stand_in.limits_for(source),
        client_bounds={"deadline_seconds": 120, "connect_timeout_seconds": 15, "max_response_bytes": 1_048_576,
                       "max_request_bytes": 65_536,
                       "max_blocks_per_page": SCAN["to_block_exclusive"] - SCAN["from_block"]})
    return OperatingRelease(release_id=release_id, kind=kind, history=part,  # type: ignore[arg-type]
                            nansen=stand_in.nansen_part(nansen_endpoint) if nansen else None)


class BoundRecordingStandIn(stand_in.RecordingStandIn):
    """The in-process stand-in provider serving the four-bucket recording."""

    def __init__(self) -> None:
        super().__init__()
        self.replies = stand_in.StandInReplies(recording())


def recording_runtime(settings: Any, *, release: OperatingRelease | None = None,
                      provider: BoundRecordingStandIn | None = None, creds: stand_in.StandInCredentials | None = None,
                      ) -> tuple[ReleasedSourceRuntime, BoundRecordingStandIn, stand_in.StandInNansen,
                                 stand_in.StandInCredentials]:
    release = release or bound_release()
    provider = provider or BoundRecordingStandIn()
    nansen = stand_in.StandInNansen()
    creds = creds or stand_in.credentials()
    runtime = open_released_runtime(settings, release, credentials=creds, http_transport=provider.transport,
                                    nansen_transport=nansen.transport if release.nansen else None)
    return runtime, provider, nansen, creds


def declare(client: Any, headers: Mapping[str, str], limits: Mapping[str, int]) -> tuple[str, str, dict[str, Any]]:
    """Save a DESCRIPTIVE declaration on the bound source through the public API. The shared request body names a
    two-hour schedule, so its decision schedule is moved inside this source's 20-minute window."""
    from research_flows import history_body, investigation_request

    bundle = investigation_request(client, headers)
    intake_id = bundle["intake"]["record_id"]
    body = history_body(client, headers, bundle, source_id=SOURCE_ID, direction="DESCRIPTIVE", bounds=dict(limits))
    body["configuration"]["schedule"] = {**body["configuration"]["schedule"],
                                         "start": iso_utc(epoch(WINDOW_START) + BUCKET_SECONDS), "end": WINDOW_END}
    saved = client.post(f"/v1/research/requests/{intake_id}/history-investigations", headers=headers, json=body)
    assert saved.status_code == 201, saved.text
    return intake_id, saved.json()["declaration"]["record_id"], body


def loopback_provider(log_path: Path, *, port: int = 0) -> stand_in.LoopbackStandInProvider:
    """The owned loopback stand-in provider serving the four-bucket recording, with the same request log.

    `operating_release_stand_in` (outside this lease) builds a provider's replies from a recording id, so its lookup is
    replaced only while this provider is constructed."""
    source = recording()  # built before the replacement: recording() itself reads stand_in.recording
    original = stand_in.recording
    stand_in.recording = lambda recording_id="": source  # type: ignore[assignment]
    try:
        return stand_in.LoopbackStandInProvider(PROFILE_ID, log_path, port=port)
    finally:
        stand_in.recording = original


def loopback_runtime_at(settings: Any, port: int, *, release_id: str = RELEASE_ID, missing: tuple[str, ...] = (),
                        nansen_port: int | None = None, binding: Any = "DEFAULT",
                        ) -> tuple[ReleasedSourceRuntime, stand_in.StandInCredentials]:
    """The bound release over the accepted network transport, reaching only the loopback stand-in on `port`; with
    `nansen_port`, the existing loopback Nansen stand-in too."""
    release = bound_release(release_id=release_id, envio_endpoint=f"http://127.0.0.1:{port}",
                            quicknode_host="127.0.0.1", nansen=nansen_port is not None,
                            nansen_endpoint=f"http://127.0.0.1:{nansen_port}", binding=binding)
    creds = stand_in.credentials(quicknode=stand_in.quicknode_url("127.0.0.1", "http", port), missing=missing)
    nansen = None if nansen_port is None else NansenHttpFactory(
        connect=stand_in.nansen_loopback_connector(nansen_port))
    return open_released_runtime(settings, release, credentials=creds, http_transport=StdlibHttpTransport,
                                 nansen_transport=nansen), creds
