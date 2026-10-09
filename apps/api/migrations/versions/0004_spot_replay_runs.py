"""P13 immutable owner-scoped replay runs.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spot_replay_runs",
        sa.Column("replay_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("strategy_revision_id", sa.UUID(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(idempotency_key) BETWEEN 1 AND 200", name="ck_spot_replay_idempotency_key"),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$' AND content_sha256 ~ '^[0-9a-f]{64}$'",
                           name="ck_spot_replay_hashes"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_spot_replay_owner"),
        sa.ForeignKeyConstraint(["owner_id", "strategy_id", "strategy_revision_id"],
                                ["strategy_revisions.owner_id", "strategy_revisions.strategy_id",
                                 "strategy_revisions.revision_id"], name="fk_spot_replay_strategy_revision"),
        sa.PrimaryKeyConstraint("replay_id"),
        sa.UniqueConstraint("owner_id", "replay_id", name="uq_spot_replay_owner_id"),
        sa.UniqueConstraint("owner_id", "method", "path", "idempotency_key", name="uq_spot_replay_idempotency"),
    )
    op.create_index("ix_spot_replay_owner_created", "spot_replay_runs", ["owner_id", "created_at"])
    op.execute("CREATE TRIGGER spot_replay_runs_immutable BEFORE UPDATE OR DELETE ON spot_replay_runs "
               "FOR EACH ROW EXECUTE FUNCTION edge_os_reject_change()")


def downgrade() -> None:
    op.execute("DROP TRIGGER spot_replay_runs_immutable ON spot_replay_runs")
    op.drop_table("spot_replay_runs")
