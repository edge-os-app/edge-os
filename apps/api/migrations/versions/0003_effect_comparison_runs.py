"""P09 separately adopted deterministic effect comparisons and immutable reports.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "effect_run_declarations",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("intake_record_id", sa.UUID(), nullable=False),
        sa.Column("p08_declaration_id", sa.UUID(), nullable=False),
        sa.Column("operation_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(idempotency_key) BETWEEN 1 AND 200", name="ck_effect_run_idempotency_key"),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="ck_effect_run_fingerprint"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_effect_run_owner"),
        sa.ForeignKeyConstraint(["owner_id", "intake_record_id"], ["records.owner_id", "records.record_id"],
                                name="fk_effect_run_intake"),
        sa.ForeignKeyConstraint(["owner_id", "intake_record_id", "p08_declaration_id"],
                                ["investigation_declarations.owner_id", "investigation_declarations.intake_record_id",
                                 "investigation_declarations.declaration_id"], name="fk_effect_run_p08_declaration"),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("owner_id", "run_id", name="uq_effect_run_owner_run"),
        sa.UniqueConstraint("owner_id", "intake_record_id", "run_id", name="uq_effect_run_owner_intake_run"),
        sa.UniqueConstraint("owner_id", "intake_record_id", "idempotency_key", name="uq_effect_run_owner_request_key"),
        sa.UniqueConstraint("owner_id", "operation_id", name="uq_effect_run_owner_operation"),
    )
    op.create_index("ix_effect_run_owner_intake", "effect_run_declarations",
                    ["owner_id", "intake_record_id", "created_at"])
    op.create_table(
        "effect_run_events",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("attempt_idempotency_key", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_effect_run_event_owner"),
        sa.ForeignKeyConstraint(["owner_id", "run_id"],
                                ["effect_run_declarations.owner_id", "effect_run_declarations.run_id"],
                                name="fk_effect_run_event_run"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("owner_id", "event_id", name="uq_effect_run_event_owner_event"),
        sa.UniqueConstraint("owner_id", "run_id", "attempt_idempotency_key", name="uq_effect_run_event_attempt_key"),
        sa.UniqueConstraint("sequence"),
    )
    op.create_index("ix_effect_run_event_owner_run", "effect_run_events", ["owner_id", "run_id", "sequence"])
    op.create_table(
        "effect_reports",
        sa.Column("report_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_effect_report_owner"),
        sa.ForeignKeyConstraint(["owner_id", "run_id"],
                                ["effect_run_declarations.owner_id", "effect_run_declarations.run_id"],
                                name="fk_effect_report_run"),
        sa.PrimaryKeyConstraint("report_id"),
        sa.UniqueConstraint("owner_id", "report_id", name="uq_effect_report_owner_report"),
        sa.UniqueConstraint("owner_id", "run_id", name="uq_effect_report_owner_run"),
    )
    op.create_index("ix_effect_report_owner_created", "effect_reports", ["owner_id", "created_at"])
    for table in ("effect_run_declarations", "effect_run_events", "effect_reports"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION edge_os_reject_change()")


def downgrade() -> None:
    for table in ("effect_reports", "effect_run_events", "effect_run_declarations"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
        op.drop_table(table)
