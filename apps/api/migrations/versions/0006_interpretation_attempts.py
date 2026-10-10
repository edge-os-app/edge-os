"""P05 append-only interpretation attempts, settlements, links and late results.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

HEX64 = "'^[0-9a-f]{64}$'"


def sha256_of(column: str) -> str:
    return f"encode(sha256(convert_to({column}, 'UTF8')), 'hex')"


def upgrade() -> None:
    op.create_table(
        "interpretation_attempts",
        sa.Column("attempt_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("intake_record_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("retry_of", sa.UUID(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("system_prompt_sha256", sa.Text(), nullable=False),
        sa.Column("task_sha256", sa.Text(), nullable=False),
        sa.Column("task_text", sa.Text(), nullable=False),
        sa.Column("response_shape_sha256", sa.Text(), nullable=False),
        sa.Column("manifest_sha256", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_sha256", sa.Text(), nullable=False),
        sa.Column("runtime_label", sa.Text(), nullable=False),
        sa.Column("answer_ref", sa.Text(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_sha256", sa.Text(), nullable=True),
        sa.Column("previous_revision_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_attempt_sequence"),
        sa.CheckConstraint("purpose IN ('INTERPRET', 'FOLLOW_UP')", name="ck_attempt_purpose"),
        sa.CheckConstraint("runtime_label IN ('LOCAL_FAKE_PROVIDER', 'LIVE')", name="ck_attempt_runtime_label"),
        sa.CheckConstraint(
            f"system_prompt_sha256 ~ {HEX64} AND task_sha256 ~ {HEX64} AND response_shape_sha256 ~ {HEX64} "
            f"AND manifest_sha256 ~ {HEX64} AND config_sha256 ~ {HEX64}", name="ck_attempt_hashes"),
        sa.CheckConstraint(f"task_sha256 = {sha256_of('task_text')}", name="ck_attempt_task_hash"),
        sa.CheckConstraint(
            "(answer_ref IS NULL) = (answer_text IS NULL) AND (answer_text IS NULL) = (answer_sha256 IS NULL)"
            f" AND (answer_text IS NULL OR answer_sha256 = {sha256_of('answer_text')})", name="ck_attempt_answer"),
        sa.CheckConstraint("(purpose = 'FOLLOW_UP') = (answer_text IS NOT NULL AND previous_revision_id IS NOT NULL)",
                           name="ck_attempt_follow_up_shape"),
        sa.CheckConstraint("retry_of IS NULL OR sequence > 1", name="ck_attempt_retry_is_later"),
        sa.ForeignKeyConstraint(["owner_id", "intake_record_id"], ["records.owner_id", "records.record_id"],
                                name="fk_attempt_intake"),
        sa.ForeignKeyConstraint(["owner_id", "previous_revision_id"], ["records.owner_id", "records.record_id"],
                                name="fk_attempt_previous_revision"),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("owner_id", "attempt_id", name="uq_attempt_owner_attempt"),
        sa.UniqueConstraint("owner_id", "intake_record_id", "attempt_id", name="uq_attempt_owner_intake_attempt"),
        sa.UniqueConstraint("owner_id", "intake_record_id", "sequence", name="uq_attempt_owner_intake_sequence"),
    )
    op.create_foreign_key(
        "fk_attempt_retry_of", "interpretation_attempts", "interpretation_attempts",
        ["owner_id", "intake_record_id", "retry_of"], ["owner_id", "intake_record_id", "attempt_id"])
    op.create_index("ix_attempt_owner_intake", "interpretation_attempts", ["owner_id", "intake_record_id", "sequence"])

    op.create_table(
        "interpretation_settlements",
        sa.Column("attempt_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("intake_record_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("total_tokens", sa.BigInteger(), nullable=True),
        sa.Column("usage_source", sa.Text(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=True),
        sa.Column("response_sha256", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("parse_result", sa.Text(), nullable=False),
        sa.Column("error_class", sa.Text(), nullable=True),
        sa.Column("runtime_observed", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('COMPLETED', 'TRUNCATED', 'PROVIDER_FAILED', 'TIMED_OUT', 'INTERRUPTED', 'UNKNOWN')",
            name="ck_settlement_status"),
        sa.CheckConstraint("usage_source IN ('UNKNOWN', 'PROVIDER_REPORTED')", name="ck_settlement_usage_source"),
        sa.CheckConstraint(
            "(usage_source = 'PROVIDER_REPORTED') = (input_tokens IS NOT NULL AND output_tokens IS NOT NULL)"
            " AND (usage_source = 'PROVIDER_REPORTED' OR (input_tokens IS NULL AND output_tokens IS NULL "
            "AND total_tokens IS NULL))"
            " AND coalesce(input_tokens, 0) >= 0 AND coalesce(output_tokens, 0) >= 0 "
            "AND coalesce(total_tokens, 0) >= 0", name="ck_settlement_usage"),
        sa.CheckConstraint("coalesce(latency_ms, 0) >= 0 AND coalesce(request_count, 0) >= 0",
                           name="ck_settlement_counts"),
        sa.CheckConstraint(
            "(response_text IS NULL) = (response_sha256 IS NULL) "
            f"AND (response_text IS NULL OR response_sha256 = {sha256_of('response_text')})",
            name="ck_settlement_response_hash"),
        sa.CheckConstraint("(status IN ('COMPLETED', 'TRUNCATED')) = (response_text IS NOT NULL)",
                           name="ck_settlement_text"),
        sa.CheckConstraint(
            "(response_text IS NULL AND parse_result = 'NOT_PARSED') "
            "OR (status = 'COMPLETED' AND (parse_result = 'ACCEPTED' OR parse_result ~ '^REJECTED:.+')) "
            "OR (status = 'TRUNCATED' AND parse_result ~ '^REJECTED:.+')", name="ck_settlement_parse_result"),
        sa.ForeignKeyConstraint(
            ["owner_id", "intake_record_id", "attempt_id"],
            ["interpretation_attempts.owner_id", "interpretation_attempts.intake_record_id",
             "interpretation_attempts.attempt_id"], name="fk_settlement_attempt"),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("owner_id", "attempt_id", name="uq_settlement_owner_attempt"),
        sa.UniqueConstraint("attempt_id", "status", name="uq_settlement_attempt_status"),
        sa.UniqueConstraint("attempt_id", "status", "parse_result", name="uq_settlement_attempt_status_parse"),
    )

    op.create_table(
        "interpretation_attempt_links",
        sa.Column("attempt_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("intake_record_id", sa.UUID(), nullable=False),
        sa.Column("revision_record_id", sa.UUID(), nullable=False),
        sa.Column("settled_status", sa.Text(), nullable=False),
        sa.Column("settled_parse_result", sa.Text(), nullable=False),
        sa.Column("offered_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("settled_status = 'COMPLETED' AND settled_parse_result = 'ACCEPTED'",
                           name="ck_attempt_link_accepted"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "settled_status", "settled_parse_result"],
            ["interpretation_settlements.attempt_id", "interpretation_settlements.status",
             "interpretation_settlements.parse_result"], name="fk_attempt_link_accepted_settlement"),
        sa.ForeignKeyConstraint(
            ["owner_id", "intake_record_id", "attempt_id"],
            ["interpretation_attempts.owner_id", "interpretation_attempts.intake_record_id",
             "interpretation_attempts.attempt_id"], name="fk_attempt_link_attempt"),
        sa.ForeignKeyConstraint(["owner_id", "revision_record_id"], ["records.owner_id", "records.record_id"],
                                name="fk_attempt_link_revision"),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("owner_id", "revision_record_id", name="uq_attempt_link_owner_revision"),
    )

    op.create_table(
        "interpretation_late_results",
        sa.Column("observation_id", sa.UUID(), nullable=False),
        sa.Column("attempt_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("intake_record_id", sa.UUID(), nullable=False),
        sa.Column("settled_status", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("total_tokens", sa.BigInteger(), nullable=True),
        sa.Column("usage_source", sa.Text(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=True),
        sa.Column("response_sha256", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("error_class", sa.Text(), nullable=True),
        sa.CheckConstraint("settled_status IN ('TIMED_OUT', 'INTERRUPTED', 'UNKNOWN')", name="ck_late_result_uncertain"),
        sa.CheckConstraint("usage_source IN ('UNKNOWN', 'PROVIDER_REPORTED')", name="ck_late_result_usage_source"),
        sa.CheckConstraint(
            "(response_text IS NULL) = (response_sha256 IS NULL) "
            f"AND (response_text IS NULL OR response_sha256 = {sha256_of('response_text')})",
            name="ck_late_result_response_hash"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "settled_status"],
            ["interpretation_settlements.attempt_id", "interpretation_settlements.status"],
            name="fk_late_result_uncertain_settlement"),
        sa.ForeignKeyConstraint(
            ["owner_id", "intake_record_id", "attempt_id"],
            ["interpretation_attempts.owner_id", "interpretation_attempts.intake_record_id",
             "interpretation_attempts.attempt_id"], name="fk_late_result_attempt"),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_index("ix_late_result_owner_intake", "interpretation_late_results",
                    ["owner_id", "intake_record_id", "observed_at"])
    for table in TABLES:
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION edge_os_reject_change()")


TABLES = ("interpretation_attempts", "interpretation_settlements", "interpretation_attempt_links",
          "interpretation_late_results")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
    op.drop_index("ix_late_result_owner_intake", table_name="interpretation_late_results")
    op.drop_table("interpretation_late_results")
    op.drop_table("interpretation_attempt_links")
    op.drop_table("interpretation_settlements")
    op.drop_index("ix_attempt_owner_intake", table_name="interpretation_attempts")
    op.drop_table("interpretation_attempts")
