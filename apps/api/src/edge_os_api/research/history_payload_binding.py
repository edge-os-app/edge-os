"""Saved-history payload binding: the application's in-process use of the accepted forward-history checker.

An operating release may name one frozen recorder handoff in `HistoryRelease.provider_facts["forward_history_binding"]`
as a legacy `{handoff_json, handoff_sha256}` anchor or a complete versioned `/2` graph. Admission validates the
matching SYNTHETIC/STAND_IN or ACTUAL version before credentials. After collection the worker saves the dataset, flushes it, reads the
stored owner-scoped row back and runs the checker on that row's own `raw_records`. One immutable
`HISTORY_PAYLOAD_BOUND` event, in the dataset transaction, keeps the exact handoff text, the report, its hash and the
checker identity.

Market adoption and history replay select that event again through the same owner, job, attempt and dataset, check its
identities and rerun the checker on the current saved raw records. A saved PASS alone grants nothing. Binding is
required for every dataset of an explicitly bound release and for every `PROVIDER_ACTUAL` dataset; other datasets are
`NOT_REQUIRED` and keep their behavior. A PASS proves payload binding only (see
`docs/qualification/forward-history-recorder/CONTRACT.md`): it never changes the P07 verdict, relabels evidence, proves
provider provenance or authorizes anything by itself.
"""

from __future__ import annotations

import datetime as dt
import functools
import hashlib
import importlib.util
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding
from edge_os_api.core.research.operating_release import BINDING_FACT, HistoryRelease, ReleaseRefused
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research.history_dataset import HistoryDatasetRow

REPO_ROOT = Path(__file__).resolve().parents[5]
CHECKER_RELATIVE_PATH = "scripts/history_payload_binding.py"
CHECKER_PATH = REPO_ROOT / CHECKER_RELATIVE_PATH
# The accepted lane 4 checker bytes. A changed checker is unavailable (INCOMPLETE) until a reviewed change pins it.
CHECKER_SHA256 = "1c74d8c9bce020e35bb372dd4a363641f1ed35566263163a9dd18807264fd667"

CHECKER_RELATIVE_PATH_V2 = "scripts/history_payload_binding_v2.py"
CHECKER_SHA256_V2 = "bec79beb0c84de56e62493078af4d9d8e4f75cd69c3968d0f1a01f2b0c1f622d"
# All trusted projection, canonicalization and time helpers, including their loaded contract assets.
CHECKER_DEPENDENCIES_V2 = {'scripts/history_payload_binding.py': '1c74d8c9bce020e35bb372dd4a363641f1ed35566263163a9dd18807264fd667',
 'apps/api/src/edge_os_api/records/contract_adapter.py': '092a87ea75384138e4663aea1d48249d9e7a8cc92a23b1d493887bae560e1b0e',
 'apps/api/src/edge_os_api/research_history/qualification_engine.py': '6cd74eefaee6a01ba81bdc7641cdf47e3cfa6edcce1cb98fec1e8ee70fc2b782',
 'docs/contracts/p02/check_contract.py': '06f3820a2ccfcf1445aef8240e5808977f8adc708ab32aecfedf28ef323d8f79',
 'docs/contracts/p02/contract.json': '1ce8a41cc6d6a097f73cf1fbd24cd8fc4d99c685c52ebf25437427a1a7948768',
 'docs/contracts/p02/fixtures/complete-strategy.json': '9ff3ab72c10616aacd37d2381a9a10500789fdbe671f2adb8314ed6a54479771',
 'docs/qualification/p07/qualification.py': '2de443a231d2b5f96090d94d6480386b42bbef6f5e1e1920b0e7903678d84ce7',
 'apps/api/src/edge_os_api/research_history/http_clients/http_transport.py': '89aa0a18442fb1a28a51d31a9a06da2da9fee4f3e2731239e34a00d44c725f0d'}

REQUIREMENT_KEY = "payload_binding_requirement"
EVENT_KIND = "HISTORY_PAYLOAD_BOUND"
EVENT_VERSION = "edge-os.history-payload-bound/1"
PRIVATE_EVENT_FIELDS = frozenset({"handoff_json", "provenance_json", "receipts_json", "raw_records"})
PASS, MISMATCH, INCOMPLETE, NOT_REQUIRED = "PASS", "MISMATCH", "INCOMPLETE", "NOT_REQUIRED"
ACTUAL_CLASS = "PROVIDER_ACTUAL"
CLAIM_LIMIT = ("Payload binding only. Not provider provenance, source rights, P07 qualification, market adoption, "
               "replay authority or execution timing.")


class CheckerUnavailable(RuntimeError):
    """The accepted checker cannot be loaded. `code` is stable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def checker(version: int = 1) -> ModuleType:
    """Check bytes on every use, including cached executions. A changed helper fails closed."""
    path = CHECKER_PATH if version == 1 else REPO_ROOT / CHECKER_RELATIVE_PATH_V2
    pin = CHECKER_SHA256 if version == 1 else CHECKER_SHA256_V2
    if version not in (1, 2):
        raise CheckerUnavailable("CHECKER_VERSION_INVALID")
    try:
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != pin:
            raise CheckerUnavailable("CHECKER_CHANGED")
        if version == 2:
            for relative, digest in CHECKER_DEPENDENCIES_V2.items():
                if hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest() != digest:
                    raise CheckerUnavailable("CHECKER_DEPENDENCY_CHANGED")
    except OSError:
        raise CheckerUnavailable("CHECKER_MISSING") from None
    return _load_checker(version, body)


@functools.lru_cache(maxsize=2)
def _load_checker(version: int, body: bytes) -> ModuleType:
    path = CHECKER_PATH if version == 1 else REPO_ROOT / CHECKER_RELATIVE_PATH_V2
    spec = importlib.util.spec_from_file_location(f"edge_os_history_payload_checker_v{version}", path)
    if spec is None:
        raise CheckerUnavailable("CHECKER_MISSING")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        exec(compile(body, str(path), "exec", dont_inherit=True), module.__dict__)
    except (OSError, ValueError, ImportError):
        raise CheckerUnavailable("CHECKER_DEPENDENCY_UNAVAILABLE") from None
    return module


checker.cache_clear = _load_checker.cache_clear  # existing tests and callers retain their explicit cache reset


def checker_identity(version: int = 1) -> dict[str, Any]:
    module = checker(version)
    identity = {"path": CHECKER_RELATIVE_PATH if version == 1 else CHECKER_RELATIVE_PATH_V2,
                "sha256": CHECKER_SHA256 if version == 1 else CHECKER_SHA256_V2,
                "report_schema": module.REPORT_SCHEMA, "canonicalization_version": module.CANONICALIZATION_VERSION}
    if version == 2:
        identity["dependencies"] = dict(CHECKER_DEPENDENCIES_V2)
    return identity


# ------------------------------------------------------------------------------------------- release definition

def _refused(detail: str) -> ReleaseRefused:
    return ReleaseRefused("forward_history_binding_invalid", detail)


def check_definition(kind: str, history: HistoryRelease) -> None:
    """Validate a release binding before effects. Pure: no credential, file write or request. Raises
    `ReleaseRefused` with a stable code; the field remains optional for STAND_IN."""
    value = history.provider_facts.get(BINDING_FACT)
    if value is None:
        if kind == "ACTUAL":
            raise ReleaseRefused("forward_history_binding_not_admitted", "ACTUAL history needs a complete /2 binding")
        return
    actual = kind == "ACTUAL"
    if kind not in ("STAND_IN", "ACTUAL"):
        raise ReleaseRefused("forward_history_binding_not_admitted",
                             "a forward history binding requires a supported release kind")
    if actual:
        if isinstance(value, Mapping) and set(value) == {"handoff_json", "handoff_sha256"}:
            raise ReleaseRefused("forward_history_binding_not_admitted", "legacy binding evidence cannot bind ACTUAL")
        _check_actual_definition(value, history)
        return
    if (not isinstance(value, Mapping) or set(value) != {"handoff_json", "handoff_sha256"}
            or not isinstance(value["handoff_json"], str) or not isinstance(value["handoff_sha256"], str)):
        raise _refused("the binding must be exactly {handoff_json: text, handoff_sha256: text}")
    try:
        module = checker()
    except CheckerUnavailable:
        raise ReleaseRefused("forward_history_checker_unavailable",
                             "the accepted payload checker is not available; nothing was read or sent") from None
    body = value["handoff_json"].encode("utf-8")
    if len(body) > module.MAX_HANDOFF_BYTES:
        raise _refused("the handoff is larger than the checker's handoff ceiling")
    if hashlib.sha256(body).hexdigest() != value["handoff_sha256"]:
        raise _refused("the handoff digest does not match its bytes")
    try:
        handoff = module.strict_json(body, "HANDOFF_NOT_STRICT_JSON")
    except module.PayloadError:
        raise _refused("the handoff is not strict JSON") from None
    if not isinstance(handoff, Mapping):
        raise _refused("the handoff is not a JSON object")
    window = ((history.profile.get("dataset") or {}).get("window") or {}) if isinstance(history.profile, Mapping) else {}
    scan = handoff.get("scan") if isinstance(handoff.get("scan"), Mapping) else {}
    handoff_window = handoff.get("window") if isinstance(handoff.get("window"), Mapping) else {}
    if handoff.get("schema_version") != module.HANDOFF_SCHEMA:
        raise _refused("the handoff has another schema version")
    if handoff.get("canonicalization_version") != module.CANONICALIZATION_VERSION:
        raise _refused("the handoff has another canonicalization version")
    if handoff.get("evidence_class") != "SYNTHETIC":
        raise _refused("only a SYNTHETIC handoff is admitted")
    if handoff.get("source_id") != history.source_id:
        raise _refused("the handoff names another source")
    if (handoff_window.get("start_utc"), handoff_window.get("end_utc")) != (window.get("start_utc"),
                                                                          window.get("end_utc")):
        raise _refused("the handoff window differs from the release profile window")
    if (scan.get("from_block"), scan.get("to_block_exclusive")) != (history.scan.get("from_block"),
                                                                  history.scan.get("to_block_exclusive")):
        raise _refused("the handoff scan differs from the release scan")


def _check_actual_definition(value: Any, history: HistoryRelease) -> None:
    try:
        module = checker(2)
    except CheckerUnavailable:
        raise ReleaseRefused("forward_history_checker_unavailable", "the accepted /2 checker is unavailable") from None
    if not isinstance(value, Mapping) or set(value) != module.ANCHOR_KEYS or value.get("schema_version") != module.ANCHOR_SCHEMA:
        raise _refused("the ACTUAL binding anchor must have the complete /2 schema")
    if not isinstance(value.get("handoff_json"), str) or not isinstance(value.get("provenance_json"), str):
        raise _refused("the ACTUAL binding must retain exact artifact texts")
    try:
        h_body, p_body = value["handoff_json"].encode("utf-8"), value["provenance_json"].encode("utf-8")
        h = module.strict_json(h_body, "HANDOFF_NOT_STRICT_JSON")
        if isinstance(h, Mapping) and h.get("schema_version") == "edge-os.forward-history-handoff/1":
            raise ReleaseRefused("forward_history_binding_not_admitted", "legacy evidence cannot bind ACTUAL")
        module.check_artifacts(h_body, p_body, {**value, "recorder_attempt_id": h.get("attempt_id")})
    except (module.PayloadError, UnicodeError, AttributeError):
        raise _refused("the ACTUAL artifact graph is incomplete or contradictory") from None
    if h["status"] != "COMPLETED" or h["clock"]["trusted"] is not True or any(
            bucket["status"] != "DELIVERED" for bucket in h["buckets"]):
        raise _refused("ACTUAL admission requires complete delivery evidence and a trusted clock")
    if h["scan"] is None:
        raise _refused("ACTUAL admission requires the complete recorded scan")
    profile = history.profile
    window = (profile.get("dataset") or {}).get("window") or {}
    roles = {token.get("role"): token.get("address") for token in profile.get("pool_tokens", [])}
    if (h["source_id"] != history.source_id or dict(h["scan"]) != dict(history.scan)
            or h["window"]["start_utc"] != window.get("start_utc") or h["window"]["end_utc"] != window.get("end_utc")
            or h["network"]["chain_id"] != (profile.get("network") or {}).get("chain_id")
            or h["market"]["pool"] != (profile.get("venue") or {}).get("pool_address")
            or h["market"]["base"] != roles.get("BASE") or h["market"]["quote"] != roles.get("QUOTE")
            or profile.get("orientation") != "QUOTE_PER_BASE"):
        raise _refused("the artifact market, source, window or scan differs from the release")


def public_definition(kind: str, history: HistoryRelease) -> dict[str, str]:
    """Keep the legacy public view; revalidate ACTUAL graphs before exposing that class."""
    if kind == "ACTUAL":
        check_definition(kind, history)
    value = history.provider_facts[BINDING_FACT]
    return {"handoff_sha256": value["handoff_sha256"], "evidence_class": "ACTUAL" if kind == "ACTUAL" else "SYNTHETIC"}


def requirement(definition: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze graph and checker identities in the attempt and dataset. Private artifact text stays in the event."""
    wanted = {"basis": "RELEASE_FORWARD_HISTORY_BINDING", "handoff_sha256": definition["handoff_sha256"]}
    if definition.get("schema_version") == "edge-os.forward-history-binding/2":
        module = checker(2)
        handoff = module.strict_json(definition["handoff_json"].encode("utf-8"), "HANDOFF_NOT_STRICT_JSON")
        wanted.update(schema_version=definition["schema_version"],
                      receipts_sha256=definition["receipts_sha256"], provenance_sha256=definition["provenance_sha256"],
                      recorder_attempt_id=handoff["attempt_id"], checker=checker_identity(2))
    return wanted


# ------------------------------------------------------------------------------------------- checker run

def _stored_row(session: Session, owner_id: uuid.UUID, dataset_id: uuid.UUID) -> HistoryDatasetRow | None:
    """The owner-scoped row as stored: attributes are reloaded from the database, never taken from memory."""
    return session.execute(select(HistoryDatasetRow).where(
        HistoryDatasetRow.owner_id == owner_id, HistoryDatasetRow.dataset_id == dataset_id)
        .execution_options(populate_existing=True)).scalar_one_or_none()


def _started(session: Session, owner_id: uuid.UUID, job_id: str, attempt_id: str) -> Any:
    """The collection attempt's own started event: the persisted identity the job froze before any effect."""
    from edge_os_api.research.investigation_jobs import InvestigationEventRow

    return session.execute(select(InvestigationEventRow).where(
        InvestigationEventRow.owner_id == owner_id, InvestigationEventRow.job_id == uuid.UUID(job_id),
        InvestigationEventRow.attempt_id == uuid.UUID(attempt_id),
        InvestigationEventRow.kind == "ATTEMPT_STARTED")).scalar_one_or_none()


def _expected(owner_id: uuid.UUID, dataset_id: uuid.UUID, started: Mapping[str, Any] | None, *,
              job_id: str | None = None, attempt_id: str | None = None) -> dict[str, Any] | None:
    """Trusted identities from application state only: the owner, the dataset row and the attempt's frozen release,
    source and handoff requirement (`started` is the attempt's started-event content). None when it froze none."""
    content = started or {}
    release = content.get("operating_release")
    wanted = content.get(REQUIREMENT_KEY)
    source_id = (content.get("input") or {}).get("source_id")
    if not isinstance(release, Mapping) or not isinstance(wanted, Mapping) or not isinstance(source_id, str):
        return None
    expected = {"owner_id": str(owner_id), "dataset_id": str(dataset_id), "source_id": source_id,
            "release": {key: release.get(key) for key in ("release_id", "sha256", "kind")},
            "handoff_sha256": wanted.get("handoff_sha256")}
    if wanted.get("schema_version") == "edge-os.forward-history-binding/2":
        expected.update({key: wanted.get(key) for key in ("schema_version", "receipts_sha256", "provenance_sha256",
                                                         "recorder_attempt_id", "checker")})
        expected.update(job_id=job_id, attempt_id=attempt_id)
    return expected


def _reason(report: Mapping[str, Any]) -> str | None:
    overall = report["overall"]
    if overall == PASS:
        return None
    for check in report["global_checks"]:
        if check["result"] == overall:
            return f"{check['check']}:{check['reason']}"
    for bucket in report["buckets"]:
        if bucket["result"] == overall:
            return f"BUCKET_{bucket['index']}:{bucket['reason']}"
    return overall


def run_checker(handoff_text: str, row: HistoryDatasetRow,
                expected: Mapping[str, Any], *, provenance_text: str | None = None
                ) -> tuple[dict[str, Any] | None, str, str | None]:
    """Run the accepted checker in process on one stored row. Returns (report or None, result, reason).

    The CLI's byte ceilings are enforced here, before the checker reads anything, because this caller bypasses the
    CLI's bounded file reads. A ceiling, a refused input or an unavailable checker is INCOMPLETE, never PASS."""
    try:
        version = 2 if expected.get("schema_version") == "edge-os.forward-history-binding/2" else 1
        if version == 1 and (expected.get("release") or {}).get("kind") == "ACTUAL":
            return None, INCOMPLETE, "forward_history_binding_not_admitted"
        module = checker(version)
        if version == 2 and expected.get("checker") != checker_identity(2):
            return None, INCOMPLETE, "CHECKER_IDENTITY_DIFFERS"
    except CheckerUnavailable as error:
        return None, INCOMPLETE, error.code
    export = {"dataset_id": str(row.dataset_id), "owner_id": str(row.owner_id), "content_sha256": row.content_sha256,
              "content": row.content, "raw_records": row.raw_records}
    handoff = handoff_text.encode("utf-8")
    try:
        sizes = (len(handoff), len(record_contract.canonical_bytes(export)),
                 len(record_contract.canonical_bytes(dict(expected))))
    except record_contract.Invalid:
        return None, INCOMPLETE, "EXPORT_NOT_CANONICAL"
    for size, limit, code in zip(sizes, (module.MAX_HANDOFF_BYTES, module.MAX_EXPORT_BYTES, module.MAX_EXPECTED_BYTES),
                                 ("HANDOFF_TOO_LARGE", "EXPORT_TOO_LARGE", "EXPECTED_TOO_LARGE")):
        if size > limit:
            return None, INCOMPLETE, code
    try:
        if version == 2:
            if not isinstance(provenance_text, str):
                return None, INCOMPLETE, "PROVENANCE_MISSING"
            report = module.check_saved_export(handoff, export, expected, provenance_bytes=provenance_text.encode("utf-8"))
        else:
            report = module.check_saved_export(handoff, export, expected)
    except module.PayloadError as error:
        return None, INCOMPLETE, error.code
    return report, report["overall"], _reason(report)


def record_binding(session: Session, *, owner_id: uuid.UUID, job_id: uuid.UUID, attempt_id: uuid.UUID,
                   dataset_id: uuid.UUID, definition: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the just-saved dataset inside its own transaction and add one `HISTORY_PAYLOAD_BOUND` event.

    Flushes the pending dataset first, then reads the stored owner-scoped row back. Every outcome is saved, including
    MISMATCH and INCOMPLETE; the dataset, its P07 verdict, raw records and bucket times are never changed."""
    from edge_os_api.research.investigation_jobs import InvestigationEventRow

    session.flush()
    row = _stored_row(session, owner_id, dataset_id)
    started = _started(session, owner_id, str(job_id), str(attempt_id))
    expected = _expected(owner_id, dataset_id, None if started is None else started.content,
                         job_id=str(job_id), attempt_id=str(attempt_id))
    if row is None or expected is None:
        report, result, reason = None, INCOMPLETE, "DATASET_OR_ATTEMPT_IDENTITY_MISSING"
    else:
        report, result, reason = run_checker(definition["handoff_json"], row, expected,
                                               provenance_text=definition.get("provenance_json"))
    try:
        identity: dict[str, Any] | None = checker_identity(
            2 if definition.get("schema_version") == "edge-os.forward-history-binding/2" else 1)
    except CheckerUnavailable:
        identity = None
    content = {"schema_version": EVENT_VERSION, "dataset_id": str(dataset_id), "result": result, "reason": reason,
               "handoff_json": definition["handoff_json"], "handoff_sha256": definition["handoff_sha256"],
               "expected": expected, "checker": identity, "report": report,
               "report_sha256": None if report is None else record_contract.sha256_hex(report)}
    if definition.get("schema_version") == "edge-os.forward-history-binding/2":
        content.update({key: definition[key] for key in ("provenance_json", "provenance_sha256", "receipts_sha256")})
    session.add(InvestigationEventRow(event_id=uuid.uuid4(), owner_id=owner_id, job_id=job_id, kind=EVENT_KIND,
                                      attempt_id=attempt_id, content=content,
                                      created_at=dt.datetime.now(dt.timezone.utc)))
    return content


# ------------------------------------------------------------------------------------------- saved state

def _state(status: str, required_by: str | None, reason: str | None, **facts: Any) -> dict[str, Any]:
    return {"status": status, "required_by": required_by, "reason": reason,
            "evidence_class": facts.get("evidence_class"), "handoff_sha256": facts.get("handoff_sha256"),
            "report_sha256": facts.get("report_sha256"), "checker_sha256": facts.get("checker_sha256"),
            "claim_limit": CLAIM_LIMIT}


def _required_by(content: Mapping[str, Any], started: Mapping[str, Any] | None) -> str | None:
    if content.get(REQUIREMENT_KEY) is not None or (started is not None and REQUIREMENT_KEY in started):
        return "RELEASE_BINDING"
    if (ACTUAL_CLASS in (content.get("evidence_class"), content.get("profile_evidence_class"))
            or (content.get("operating_release") or {}).get("kind") == "ACTUAL"):
        return ACTUAL_CLASS
    return None


def binding_state(session: Session, row: HistoryDatasetRow, owner_id: uuid.UUID) -> dict[str, Any]:
    """The dataset's current binding: the saved event re-checked and the checker rerun on the current saved data.

    `owner_id` is the authenticated owner. Every identity comes from saved application state; nothing from a request.
    The records are selected here; `evaluate` decides."""
    from edge_os_api.research.investigation_jobs import InvestigationEventRow

    content = row.content
    started = event = stored = None
    if "operating_release" in content and isinstance(content.get("job_id"), str):
        started = _started(session, owner_id, content["job_id"], content["attempt_id"])
    if started is not None:
        event = session.execute(select(InvestigationEventRow).where(
            InvestigationEventRow.owner_id == owner_id, InvestigationEventRow.job_id == started.job_id,
            InvestigationEventRow.attempt_id == started.attempt_id,
            InvestigationEventRow.kind == EVENT_KIND)).scalar_one_or_none()
    if event is not None:
        stored = _stored_row(session, owner_id, row.dataset_id)
    return evaluate(content, row.dataset_id, owner_id, None if started is None else started.content,
                    None if event is None else event.content, stored)


def evaluate(content: Mapping[str, Any], dataset_id: uuid.UUID, owner_id: uuid.UUID,
             started: Mapping[str, Any] | None, saved: Mapping[str, Any] | None,
             stored: HistoryDatasetRow | None) -> dict[str, Any]:
    """Decide a binding from the selected records: the dataset content, its attempt's started event, its saved
    `HISTORY_PAYLOAD_BOUND` event and the stored row. Pure; the checker reruns on `stored`, never on the saved report.

    A saved PASS grants nothing: the rerun must PASS and reproduce the saved report hash exactly. A binding saved
    without a report (refused or checker unavailable) stays INCOMPLETE."""
    required_by = _required_by(content, started)
    if required_by is None:
        return _state(NOT_REQUIRED, None, None)
    expected = _expected(owner_id, dataset_id, started, job_id=content.get("job_id"),
                         attempt_id=content.get("attempt_id"))
    if expected is None or started is None:
        return _state(INCOMPLETE, required_by, "BINDING_REQUIREMENT_MISSING")
    if content.get(REQUIREMENT_KEY) != started[REQUIREMENT_KEY]:
        return _state(MISMATCH, required_by, "REQUIREMENT_DIFFERS")
    if saved is None:
        return _state(INCOMPLETE, required_by, "BINDING_EVENT_MISSING", handoff_sha256=expected["handoff_sha256"])
    handoff_text = saved.get("handoff_json")
    facts = {"handoff_sha256": expected["handoff_sha256"], "checker_sha256": (saved.get("checker") or {}).get("sha256")}
    if saved.get("dataset_id") != str(dataset_id) or saved.get("expected") != expected:
        return _state(MISMATCH, required_by, "BINDING_EVENT_IDENTITY_DIFFERS", **facts)
    if (not isinstance(handoff_text, str) or saved.get("handoff_sha256") != expected["handoff_sha256"]
            or hashlib.sha256(handoff_text.encode("utf-8")).hexdigest() != expected["handoff_sha256"]):
        return _state(MISMATCH, required_by, "HANDOFF_DIFFERS", **facts)
    saved_report = saved.get("report")
    if saved_report is not None and record_contract.sha256_hex(saved_report) != saved.get("report_sha256"):
        return _state(MISMATCH, required_by, "SAVED_REPORT_HASH_DIFFERS", **facts)
    if saved_report is None:  # a binding refused or unavailable when saved stays incomplete; a later rerun cannot fill it
        return _state(INCOMPLETE, required_by, f"SAVED_{saved.get('reason') or 'REPORT_MISSING'}", **facts)
    version = 2 if expected.get("schema_version") == "edge-os.forward-history-binding/2" else 1
    if facts["checker_sha256"] != (CHECKER_SHA256_V2 if version == 2 else CHECKER_SHA256):
        return _state(INCOMPLETE, required_by, "CHECKER_IDENTITY_DIFFERS", **facts)
    if stored is None:
        return _state(INCOMPLETE, required_by, "DATASET_MISSING", **facts)
    if version == 2:
        try:
            current_identity = checker_identity(2)
        except CheckerUnavailable as error:
            return _state(INCOMPLETE, required_by, error.code, **facts)
        if saved.get("checker") != expected.get("checker") or saved.get("checker") != current_identity:
            return _state(INCOMPLETE, required_by, "CHECKER_IDENTITY_DIFFERS", **facts)
        if any(saved.get(key) != expected.get(key) for key in ("receipts_sha256", "provenance_sha256")):
            return _state(MISMATCH, required_by, "ARTIFACT_IDENTITY_DIFFERS", **facts)
    report, result, reason = run_checker(handoff_text, stored, expected, provenance_text=saved.get("provenance_json"))
    report_sha256 = None if report is None else record_contract.sha256_hex(report)
    facts.update(report_sha256=report_sha256, evidence_class=_handoff_class(handoff_text))
    if result == PASS and report_sha256 != saved.get("report_sha256"):
        return _state(MISMATCH, required_by, "SAVED_REPORT_DIFFERS", **facts)
    return _state(result, required_by, reason, **facts)


def _handoff_class(handoff_text: str) -> str | None:
    try:
        handoff = checker().strict_json(handoff_text.encode("utf-8"), "HANDOFF_NOT_STRICT_JSON")
    except (CheckerUnavailable, ValueError):
        return None
    return handoff.get("evidence_class") if isinstance(handoff, Mapping) else None


def require_bound(session: Session, principal: Principal, row: HistoryDatasetRow, *, stage: str,
                  path: str) -> dict[str, Any]:
    """The consumer guard. PASS and NOT_REQUIRED continue; MISMATCH and INCOMPLETE refuse before any write."""
    state = binding_state(session, row, principal.user_id)
    if state["status"] == MISMATCH:
        raise AppError(409, stage, "CONFLICTED", "payload_binding_mismatch", [finding(
            "payload_binding_mismatch", path, "The saved history does not match its recorded delivery "
            f"({state['reason']}). It cannot be used. The saved verdict and data stay unchanged.")])
    if state["status"] == INCOMPLETE:
        raise AppError(409, stage, "UNAVAILABLE", "payload_binding_incomplete", [finding(
            "payload_binding_incomplete", path, "This saved history needs a complete payload binding before use "
            f"({state['reason']}). Nothing was changed.")])
    return state


def lineage(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """The binding identity a consumer saves beside its result. None when no binding is required, so unbound saved
    snapshots keep their exact bytes."""
    if state["status"] == NOT_REQUIRED:
        return None
    return {key: state[key] for key in ("status", "required_by", "evidence_class", "handoff_sha256", "report_sha256",
                                        "checker_sha256")}


def public_event(kind: str, content: Mapping[str, Any]) -> Mapping[str, Any]:
    """An owner-facing binding event: recursively replace known private artifact fields with sizes or counts."""
    if kind != EVENT_KIND:
        return content
    def redact(value: Any) -> Any:
        if isinstance(value, Mapping):
            shown = {}
            for key, item in value.items():
                if key in PRIVATE_EVENT_FIELDS:
                    size_key = key.removesuffix("_json") + "_bytes" if key.endswith("_json") else "raw_record_count"
                    shown[size_key] = len(item.encode("utf-8")) if isinstance(item, str) else len(item) if isinstance(item, list) else None
                else:
                    shown[key] = redact(item)
            return shown
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value
    return redact(content)
