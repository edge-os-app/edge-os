"""#58 Hermes mount: the shared provider spend ledger.

Revision ID: 0013
Revises: 0012

`usage_local.provider_spend_settings` holds the one frozen configuration (global and owner caps in nano-USD, exact
token prices). `provider_spend_reservations` holds one reservation per saved interpretation attempt, with that
attempt's owner and saved request, copied from the append-only attempt row inside the reserving transaction. `provider_spend_events` is append-only. No existing row
changes. The downgrade refuses while any reservation or event exists, because it would lose recorded spending liability
or a recorded cap decision.
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

SCHEMA = "usage_local"


def upgrade() -> None:
    op.create_table('provider_spend_settings',
    sa.Column('settings_id', sa.SmallInteger(), nullable=False),
    sa.Column('global_cap_nano_usd', sa.BigInteger(), nullable=False),
    sa.Column('owner_cap_nano_usd', sa.BigInteger(), nullable=False),
    sa.Column('prompt_usd_per_million', sa.Text(), nullable=False),
    sa.Column('completion_usd_per_million', sa.Text(), nullable=False),
    sa.Column('cap_source', sa.Text(), nullable=False),
    sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('settings_id = 1', name='provider_spend_settings_single_check'),
    sa.CheckConstraint('global_cap_nano_usd >= 0 AND owner_cap_nano_usd >= 0',
                       name=op.f('provider_spend_settings_caps_check')),
    sa.PrimaryKeyConstraint('settings_id', name=op.f('provider_spend_settings_pkey')),
    schema=SCHEMA
    )
    op.create_table('provider_spend_reservations',
    sa.Column('attempt_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('intake_record_id', sa.UUID(), nullable=False),
    sa.Column('scope', sa.Text(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('reserved_nano_usd', sa.BigInteger(), nullable=False),
    sa.Column('charged_nano_usd', sa.BigInteger(), nullable=True),
    sa.Column('max_input_tokens', sa.BigInteger(), nullable=False),
    sa.Column('max_output_tokens', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("state IN ('RESERVED', 'UNKNOWN', 'SETTLED', 'RELEASED')",
                       name=op.f('provider_spend_reservations_state_check')),
    sa.CheckConstraint('reserved_nano_usd >= 0 AND (charged_nano_usd IS NULL OR charged_nano_usd >= 0)',
                       name=op.f('provider_spend_reservations_amounts_check')),
    sa.CheckConstraint("(state = 'SETTLED') = (charged_nano_usd IS NOT NULL)",
                       name=op.f('provider_spend_reservations_charge_check')),
    sa.PrimaryKeyConstraint('attempt_id', name=op.f('provider_spend_reservations_pkey')),
    schema=SCHEMA
    )
    op.create_index('ix_provider_spend_owner_state', 'provider_spend_reservations', ['owner_id', 'state'],
                    unique=False, schema=SCHEMA)
    op.create_index('ix_provider_spend_scope_state', 'provider_spend_reservations', ['scope', 'state'],
                    unique=False, schema=SCHEMA)
    op.create_table('provider_spend_events',
    sa.Column('seq', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('attempt_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('nano_usd', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('seq', name=op.f('provider_spend_events_pkey')),
    schema=SCHEMA
    )
    op.create_index('ix_provider_spend_events_attempt', 'provider_spend_events', ['attempt_id', 'seq'],
                    unique=False, schema=SCHEMA)
    op.execute(f"CREATE TRIGGER provider_spend_events_immutable BEFORE UPDATE OR DELETE ON {SCHEMA}.provider_spend_events "
               "FOR EACH ROW EXECUTE FUNCTION public.edge_os_reject_change()")


def downgrade() -> None:
    # Revision 0012 cannot hold spending liability or a recorded cap decision. Refuse instead of dropping them.
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM {SCHEMA}.provider_spend_reservations)
                    OR EXISTS (SELECT 1 FROM {SCHEMA}.provider_spend_events) THEN
                RAISE EXCEPTION 'downgrade below 0013 refused: provider spend reservations or events exist';
            END IF;
        END $$""")
    op.drop_table('provider_spend_events', schema=SCHEMA)
    op.drop_index('ix_provider_spend_scope_state', table_name='provider_spend_reservations', schema=SCHEMA)
    op.drop_index('ix_provider_spend_owner_state', table_name='provider_spend_reservations', schema=SCHEMA)
    op.drop_table('provider_spend_reservations', schema=SCHEMA)
    op.drop_table('provider_spend_settings', schema=SCHEMA)
