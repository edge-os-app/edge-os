"""#58 Stage 2: shared owner and global usage quotas; request rate windows.

Revision ID: 0010
Revises: 0009

`usage_local` holds frozen-cap allocations per scope (GLOBAL or OWNER) and resource, one reservation per original
subject, an append-only event history, and per-owner request rate windows. The research budget rows from 0009 move
into OWNER allocations with their caps and totals unchanged. Each research job that still holds a reservation gets
its original reservation row. GLOBAL allocations start with the sum of the moved totals and the default cap
(`cap_source = migration-0010-default`). Then `research_local.research_budgets` is dropped. Downgrade restores that
table from the OWNER allocations.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

SCHEMA = "usage_local"
GLOBAL_OWNER = "00000000-0000-0000-0000-000000000000"
DEFAULT_GLOBAL = {"provider_requests": 100000, "compute_seconds": 10_000_000}


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table('usage_allocations',
    sa.Column('allocation_id', sa.UUID(), nullable=False),
    sa.Column('scope', sa.Text(), nullable=False),
    sa.Column('owner_key', sa.UUID(), nullable=False),
    sa.Column('resource', sa.Text(), nullable=False),
    sa.Column('cap', sa.BigInteger(), nullable=False),
    sa.Column('cap_source', sa.Text(), nullable=False),
    sa.Column('reserved', sa.BigInteger(), nullable=False),
    sa.Column('consumed', sa.BigInteger(), nullable=False),
    sa.Column('unknown', sa.BigInteger(), nullable=False),
    sa.Column('overrun', sa.BigInteger(), nullable=False),
    sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("scope IN ('GLOBAL', 'OWNER')", name=op.f('usage_allocations_scope_check')),
    sa.CheckConstraint('cap >= 0 AND reserved >= 0 AND consumed >= 0 AND unknown >= 0 AND overrun >= 0',
                       name=op.f('usage_allocations_amounts_check')),
    sa.PrimaryKeyConstraint('allocation_id', name=op.f('usage_allocations_pkey')),
    sa.UniqueConstraint('scope', 'owner_key', 'resource', name='uq_usage_allocation_scope'),
    schema=SCHEMA
    )
    op.create_table('usage_reservations',
    sa.Column('reservation_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('subject_kind', sa.Text(), nullable=False),
    sa.Column('subject_id', sa.Text(), nullable=False),
    sa.Column('amounts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('settled', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('reservation_id', name=op.f('usage_reservations_pkey')),
    sa.UniqueConstraint('subject_kind', 'subject_id', name='uq_usage_reservation_subject'),
    schema=SCHEMA
    )
    op.create_index(op.f('usage_local_usage_reservations_owner_id_idx'), 'usage_reservations', ['owner_id'],
                    unique=False, schema=SCHEMA)
    op.create_table('usage_events',
    sa.Column('seq', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('reservation_id', sa.UUID(), nullable=True),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('seq', name=op.f('usage_events_pkey')),
    schema=SCHEMA
    )
    op.create_table('request_windows',
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('requests', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('owner_id', 'window_start', name=op.f('request_windows_pkey')),
    schema=SCHEMA
    )
    op.execute(f"CREATE TRIGGER usage_events_immutable BEFORE UPDATE OR DELETE ON {SCHEMA}.usage_events "
               "FOR EACH ROW EXECUTE FUNCTION public.edge_os_reject_change()")

    # Move the 0009 owner budgets with caps and totals unchanged.
    for resource, cap, reserved, consumed, unknown in (
            ("provider_requests", "provider_requests_limit", "reserved_provider_requests",
             "consumed_provider_requests", "unknown_provider_requests"),
            ("compute_seconds", "compute_seconds_limit", "reserved_compute_seconds", "consumed_compute_seconds",
             "unknown_compute_seconds")):
        op.execute(f"""
            INSERT INTO {SCHEMA}.usage_allocations (allocation_id, scope, owner_key, resource, cap, cap_source,
                reserved, consumed, unknown, overrun, frozen_at, updated_at)
            SELECT gen_random_uuid(), 'OWNER', owner_id, '{resource}', {cap}, 'migration-0010-from-research-budgets',
                   {reserved}, {consumed}, {unknown}, 0, updated_at, updated_at
            FROM research_local.research_budgets""")
        op.execute(f"""
            INSERT INTO {SCHEMA}.usage_allocations (allocation_id, scope, owner_key, resource, cap, cap_source,
                reserved, consumed, unknown, overrun, frozen_at, updated_at)
            SELECT gen_random_uuid(), 'GLOBAL', '{GLOBAL_OWNER}', '{resource}', {DEFAULT_GLOBAL[resource]},
                   'migration-0010-default', COALESCE(SUM({reserved}), 0), COALESCE(SUM({consumed}), 0),
                   COALESCE(SUM({unknown}), 0), 0, now(), now()
            FROM research_local.research_budgets HAVING COUNT(*) > 0""")
    # Each job that still holds an open reservation keeps its original reservation; settled parts stay settled.
    op.execute(f"""
        INSERT INTO {SCHEMA}.usage_reservations (reservation_id, owner_id, subject_kind, subject_id, amounts,
            settled, created_at)
        SELECT gen_random_uuid(), owner_id, 'investigation_job', job_id::text,
               jsonb_build_object('provider_requests', (budget->'reserved'->>'provider_requests')::bigint,
                                  'compute_seconds', (budget->'reserved'->>'compute_seconds')::bigint),
               (CASE WHEN (budget->'settled'->>'provider_requests')::bigint >=
                          (budget->'reserved'->>'provider_requests')::bigint
                     THEN jsonb_build_object('provider_requests', jsonb_build_object('kind', 'MIGRATED'))
                     ELSE '{{}}'::jsonb END)
               || (CASE WHEN (budget->'settled'->>'compute_seconds')::bigint >=
                             (budget->'reserved'->>'compute_seconds')::bigint
                        THEN jsonb_build_object('compute_seconds', jsonb_build_object('kind', 'MIGRATED'))
                        ELSE '{{}}'::jsonb END),
               created_at
        FROM research_local.investigation_jobs
        WHERE (budget->'reserved'->>'provider_requests')::bigint > 0
           OR (budget->'reserved'->>'compute_seconds')::bigint > 0""")
    op.drop_table('research_budgets', schema='research_local')


def downgrade() -> None:
    op.create_table('research_budgets',
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('provider_requests_limit', sa.Integer(), nullable=False),
    sa.Column('compute_seconds_limit', sa.Integer(), nullable=False),
    sa.Column('reserved_provider_requests', sa.Integer(), nullable=False),
    sa.Column('reserved_compute_seconds', sa.Integer(), nullable=False),
    sa.Column('consumed_provider_requests', sa.Integer(), nullable=False),
    sa.Column('consumed_compute_seconds', sa.Integer(), nullable=False),
    sa.Column('unknown_provider_requests', sa.Integer(), nullable=False),
    sa.Column('unknown_compute_seconds', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('owner_id', name=op.f('research_budgets_pkey')),
    schema='research_local'
    )
    op.execute(f"""
        INSERT INTO research_local.research_budgets
        SELECT p.owner_key, p.cap, c.cap, p.reserved, c.reserved, p.consumed, c.consumed,
               p.unknown, c.unknown, GREATEST(p.updated_at, c.updated_at)
        FROM {SCHEMA}.usage_allocations p JOIN {SCHEMA}.usage_allocations c
          ON c.owner_key = p.owner_key AND c.scope = 'OWNER' AND c.resource = 'compute_seconds'
        WHERE p.scope = 'OWNER' AND p.resource = 'provider_requests'""")
    op.execute(f"DROP TRIGGER usage_events_immutable ON {SCHEMA}.usage_events")
    op.drop_table('request_windows', schema=SCHEMA)
    op.drop_table('usage_events', schema=SCHEMA)
    op.drop_index(op.f('usage_local_usage_reservations_owner_id_idx'), table_name='usage_reservations',
                  schema=SCHEMA)
    op.drop_table('usage_reservations', schema=SCHEMA)
    op.drop_table('usage_allocations', schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} RESTRICT")
