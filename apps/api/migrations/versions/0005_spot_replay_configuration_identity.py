"""Bind each owner-scoped P13 configuration ID to its immutable input snapshot.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_SCHEMA_VERSION = "p13.spot-replay-run/1"
_ESSENTIAL_SCHEMA_VERSION = "p12.essential-evidence/1"
_INPUT_FIELDS = {
    "profile_version", "strategy_revision_id", "strategy_id", "strategy_sha256", "strategy",
    "run_configuration_id", "dataset_fixture_id", "dataset_revision_id", "dataset_qualification",
    "coverage_complete", "evidence_class", "fixture_sha256", "profile_sha256", "market_binding_id",
    "window_start", "window_end", "initial_cash_quote", "initial_base_amount", "initial_basis_quote",
    "essential_evidence", "buckets", "fixture_limitation",
}
_CONTENT_FIELDS = {
    "schema_version", "owner_id", "replay_id", "strategy_revision_id", "dataset_fixture_id",
    "run_configuration_id", "idempotency", "inputs", "result", "notice",
}


def _canonical_bytes(value: Any) -> bytes:
    def validate(node: Any) -> None:
        if isinstance(node, float):
            raise ValueError("JSON floating-point value is not canonical")
        if isinstance(node, str):
            if unicodedata.normalize("NFC", node) != node or any(0xD800 <= ord(char) <= 0xDFFF for char in node):
                raise ValueError("JSON string is not canonical")
        elif isinstance(node, list):
            for item in node:
                validate(item)
        elif isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str):
                    raise ValueError("JSON object key is not a string")
                validate(key)
                validate(item)
        elif node is not None and not isinstance(node, (bool, int)):
            raise ValueError("unsupported JSON value")

    validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _configuration_sha256(inputs: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes({"schema_version": _SCHEMA_VERSION, "inputs": inputs})).hexdigest()


def _valid_essential_fields(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"entry", "exit"}:
        return False
    for field in value.values():
        if (not isinstance(field, dict) or set(field) != {"state", "essential_dependencies"}
                or not isinstance(field.get("state"), str)
                or field.get("state") not in {"BOUND", "UNBOUND"}):
            return False
        dependencies = field.get("essential_dependencies")
        if dependencies is None:
            continue
        if not isinstance(dependencies, list) or len(dependencies) > 64:
            return False
        for dependency in dependencies:
            if not isinstance(dependency, dict) or set(dependency) != {"series", "offset_buckets"}:
                return False
            series = dependency.get("series")
            offset = dependency.get("offset_buckets")
            if (not isinstance(series, str) or series not in {"price", "quote_volume"}
                    or isinstance(offset, bool) or not isinstance(offset, int) or offset > 0):
                return False
    return True


def upgrade() -> None:
    op.create_table(
        "spot_replay_configurations",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("run_configuration_id", sa.Text(), nullable=False),
        sa.Column("configuration_sha256", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(run_configuration_id) BETWEEN 1 AND 200",
                           name="ck_spot_replay_configuration_id_length"),
        sa.CheckConstraint("configuration_sha256 ~ '^[0-9a-f]{64}$'",
                           name="ck_spot_replay_configuration_hash"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_spot_replay_configuration_owner"),
        sa.PrimaryKeyConstraint("owner_id", "run_configuration_id",
                                name="pk_spot_replay_configurations"),
    )
    op.execute("CREATE TRIGGER spot_replay_configurations_immutable BEFORE UPDATE OR DELETE "
               "ON spot_replay_configurations FOR EACH ROW EXECUTE FUNCTION edge_os_reject_change()")

    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT replay_id, owner_id, strategy_id, strategy_revision_id, content, content_sha256 "
        "FROM spot_replay_runs ORDER BY created_at, replay_id"))
    bindings: dict[tuple[Any, str], str] = {}
    for row in rows.mappings():
        content = row["content"]
        if (not isinstance(content, dict) or set(content) != _CONTENT_FIELDS
                or content.get("schema_version") != _SCHEMA_VERSION):
            raise RuntimeError("cannot bind P13 configuration IDs: a saved replay has an unsupported schema")
        run_configuration_id = content.get("run_configuration_id")
        inputs = content.get("inputs")
        row_replay_id = str(row["replay_id"])
        row_strategy_id = str(row["strategy_id"])
        row_revision_id = str(row["strategy_revision_id"])
        if (not isinstance(run_configuration_id, str) or not 1 <= len(run_configuration_id) <= 200
                or not isinstance(inputs, dict) or set(inputs) != _INPUT_FIELDS
                or content.get("replay_id") != row_replay_id
                or content.get("strategy_revision_id") != row_revision_id
                or inputs.get("run_configuration_id") != run_configuration_id
                or inputs.get("strategy_id") != row_strategy_id
                or inputs.get("strategy_revision_id") != row_revision_id
                or inputs.get("dataset_fixture_id") != content.get("dataset_fixture_id")
                or content.get("owner_id") != str(row["owner_id"])
                or not isinstance(inputs.get("strategy"), dict)
                or inputs["strategy"].get("strategy_id") != row_strategy_id):
            raise RuntimeError("cannot bind P13 configuration IDs: a saved replay identity is malformed")
        descriptor = inputs.get("essential_evidence")
        if (not isinstance(descriptor, dict)
                or set(descriptor) != {"schema_version", "strategy_revision", "run_configuration_id",
                                       "dataset_revision", "market_binding_id", "fields"}
                or descriptor.get("schema_version") != _ESSENTIAL_SCHEMA_VERSION
                or descriptor.get("strategy_revision") != inputs.get("strategy_revision_id")
                or descriptor.get("run_configuration_id") != run_configuration_id
                or descriptor.get("dataset_revision") != inputs.get("dataset_revision_id")
                or descriptor.get("market_binding_id") != inputs.get("market_binding_id")
                or not _valid_essential_fields(descriptor.get("fields"))):
            raise RuntimeError("cannot bind P13 configuration IDs: a saved essential descriptor is malformed")
        try:
            actual_content_sha256 = hashlib.sha256(_canonical_bytes(content)).hexdigest()
        except (TypeError, ValueError):
            raise RuntimeError("cannot bind P13 configuration IDs: a saved replay is not canonical JSON") from None
        if actual_content_sha256 != row["content_sha256"]:
            raise RuntimeError("cannot bind P13 configuration IDs: a saved replay content hash is invalid")
        try:
            strategy_sha256 = hashlib.sha256(_canonical_bytes(inputs["strategy"])).hexdigest()
            if strategy_sha256 != inputs.get("strategy_sha256"):
                raise ValueError("saved strategy hash mismatch")
            fingerprint = _configuration_sha256(inputs)
        except (TypeError, ValueError):
            raise RuntimeError("cannot bind P13 configuration IDs: saved replay inputs are not canonical JSON") from None
        key = (row["owner_id"], run_configuration_id)
        previous = bindings.setdefault(key, fingerprint)
        if previous != fingerprint:
            raise RuntimeError("cannot bind P13 configuration IDs: existing owner-scoped history has conflicting inputs")

    if bindings:
        registry = sa.table(
            "spot_replay_configurations",
            sa.column("owner_id", postgresql.UUID(as_uuid=True)),
            sa.column("run_configuration_id", sa.Text()),
            sa.column("configuration_sha256", sa.Text()),
        )
        op.bulk_insert(registry, [
            {"owner_id": owner_id, "run_configuration_id": run_configuration_id,
             "configuration_sha256": fingerprint}
            for (owner_id, run_configuration_id), fingerprint in bindings.items()
        ])


def downgrade() -> None:
    connection = op.get_bind()
    has_replay_history = connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM spot_replay_runs)")).scalar_one()
    if has_replay_history:
        raise RuntimeError("cannot remove immutable P13 configuration bindings while replay history exists")
    op.execute("DROP TRIGGER spot_replay_configurations_immutable ON spot_replay_configurations")
    op.drop_table("spot_replay_configurations")
