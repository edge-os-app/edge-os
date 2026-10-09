"""P08 append-only investigation declarations and access history.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_declarations",
        sa.Column("declaration_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("intake_record_id", sa.UUID(), nullable=False),
        sa.Column("edge_id", sa.UUID(), nullable=False),
        sa.Column("edge_version", sa.Integer(), nullable=False),
        sa.Column("parent_declaration_id", sa.UUID(), nullable=True),
        sa.Column("operation_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("edge_version >= 1", name="ck_investigation_edge_version"),
        sa.CheckConstraint("length(idempotency_key) BETWEEN 1 AND 200", name="ck_investigation_idempotency_key"),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="ck_investigation_fingerprint"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_investigation_owner"),
        sa.ForeignKeyConstraint(["owner_id", "intake_record_id"], ["records.owner_id", "records.record_id"],
                                name="fk_investigation_intake"),
        sa.ForeignKeyConstraint(["owner_id", "intake_record_id", "parent_declaration_id"],
                                ["investigation_declarations.owner_id", "investigation_declarations.intake_record_id",
                                 "investigation_declarations.declaration_id"], name="fk_investigation_parent"),
        sa.PrimaryKeyConstraint("declaration_id"),
        sa.UniqueConstraint("owner_id", "declaration_id", name="uq_investigation_owner_declaration"),
        sa.UniqueConstraint("owner_id", "intake_record_id", "declaration_id",
                            name="uq_investigation_owner_intake_declaration"),
        sa.UniqueConstraint("owner_id", "intake_record_id", "idempotency_key",
                            name="uq_investigation_owner_request_key"),
        sa.UniqueConstraint("owner_id", "operation_id", name="uq_investigation_owner_operation"),
        sa.UniqueConstraint("owner_id", "edge_id", "edge_version", name="uq_investigation_edge_version"),
    )
    op.create_index("ix_investigation_owner_intake", "investigation_declarations",
                    ["owner_id", "intake_record_id", "created_at"])
    op.create_table(
        "investigation_access_events",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("declaration_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id", "declaration_id"],
                                ["investigation_declarations.owner_id", "investigation_declarations.declaration_id"],
                                name="fk_investigation_access_declaration"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("owner_id", "event_id", name="uq_investigation_access_owner_event"),
        sa.UniqueConstraint("sequence"),
    )
    op.create_index("ix_investigation_access_owner_declaration", "investigation_access_events",
                    ["owner_id", "declaration_id", "sequence"])
    for table in ("investigation_declarations", "investigation_access_events"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION edge_os_reject_change()")


def downgrade() -> None:
    for table in ("investigation_access_events", "investigation_declarations"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
        op.drop_table(table)
