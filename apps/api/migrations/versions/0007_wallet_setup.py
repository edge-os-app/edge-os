"""P17 durable wallet-setup tables: one setup row per agent, append-only events and separate denials.

Revision ID: 0007
Revises: 0006

The wallet-setup package keeps its own `wallet_setup_local` metadata, so these tables are not part
of `records.Base`. They are created here so the application can persist a setup through the normal
additive migration path. `owner_id` follows the verified `users.id` by application convention and
carries no foreign key, matching the accepted local package.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_setups",
        sa.Column("setup_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("network_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("strategy_revision_id", sa.UUID(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("manifest_sha256", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("cancellation_intent", sa.Text(), server_default=sa.text("'NONE'"), nullable=False),
        sa.Column("creation_dispatched", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("request_key", sa.Text(), nullable=False),
        sa.Column("wallet_id", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("network_id IN (143, 10143)", name="ck_wallet_setup_network"),
        sa.CheckConstraint("state IN ('REQUESTED', 'PENDING', 'UNKNOWN', 'CONFIRMED', 'FAILED')",
                           name="ck_wallet_setup_state"),
        sa.CheckConstraint("cancellation_intent IN ('NONE', 'REQUESTED_BEFORE_DISPATCH', 'REQUESTED_AFTER_DISPATCH')",
                           name="ck_wallet_setup_cancellation_intent"),
        sa.CheckConstraint("length(agent_id) BETWEEN 1 AND 64", name="ck_wallet_setup_agent_id"),
        sa.CheckConstraint("length(request_key) BETWEEN 1 AND 200", name="ck_wallet_setup_request_key"),
        sa.PrimaryKeyConstraint("setup_id"),
        sa.UniqueConstraint("owner_id", "agent_id", name="uq_wallet_setup_owner_agent"),
        sa.UniqueConstraint("owner_id", "wallet_id", name="uq_wallet_setup_owner_wallet"),
    )
    op.create_index("ix_wallet_setup_owner_state", "wallet_setups", ["owner_id", "state"], unique=False)

    op.create_table(
        "wallet_setup_events",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("setup_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("sequence"),
    )
    op.create_index("ix_wallet_setup_event_setup", "wallet_setup_events", ["setup_id", "sequence"], unique=False)

    op.create_table(
        "wallet_setup_denials",
        sa.Column("denial_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("denial_id"),
    )
    op.create_index("ix_wallet_setup_denial_owner", "wallet_setup_denials", ["owner_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_wallet_setup_denial_owner", table_name="wallet_setup_denials")
    op.drop_table("wallet_setup_denials")
    op.drop_index("ix_wallet_setup_event_setup", table_name="wallet_setup_events")
    op.drop_table("wallet_setup_events")
    op.drop_index("ix_wallet_setup_owner_state", table_name="wallet_setups")
    op.drop_table("wallet_setups")
