"""#58 Task 6 recorded-history research: datasets, investigation jobs, events, budgets and reports.

Revision ID: 0009
Revises: 0008

The `research_local` schema holds the owner-scoped recorded-history datasets, original investigation jobs, their
append-only event history, per-owner research budgets and immutable investigation reports. Datasets, events and
reports reject any update or delete. No existing table, key or saved row changes.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

SCHEMA = "research_local"
IMMUTABLE = ("history_datasets", "investigation_events", "investigation_reports")


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table('history_datasets',
    sa.Column('dataset_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('declaration_id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('attempt_id', sa.UUID(), nullable=False),
    sa.Column('content_sha256', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('raw_records', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name=op.f('history_datasets_hash_check')),
    sa.PrimaryKeyConstraint('dataset_id', name=op.f('history_datasets_pkey')),
    sa.UniqueConstraint('attempt_id', name=op.f('history_datasets_attempt_id_key')),
    sa.UniqueConstraint('job_id', name=op.f('history_datasets_job_id_key')),
    schema=SCHEMA
    )
    op.create_index(op.f('research_local_history_datasets_owner_id_idx'), 'history_datasets', ['owner_id'], unique=False, schema=SCHEMA)
    op.create_table('investigation_jobs',
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('intake_record_id', sa.UUID(), nullable=False),
    sa.Column('declaration_id', sa.UUID(), nullable=False),
    sa.Column('request_key', sa.Text(), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('fingerprint', sa.Text(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('budget', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dataset_id', sa.UUID(), nullable=True),
    sa.Column('report_id', sa.UUID(), nullable=True),
    sa.Column('terminal_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('job_id', name=op.f('investigation_jobs_pkey')),
    sa.UniqueConstraint('owner_id', 'declaration_id', 'request_key', name='uq_investigation_job_key'),
    sa.UniqueConstraint('owner_id', 'operation_id', name='uq_investigation_job_operation'),
    schema=SCHEMA
    )
    op.create_table('investigation_events',
    sa.Column('seq', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('attempt_id', sa.UUID(), nullable=True),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('seq', name=op.f('investigation_events_pkey')),
    sa.UniqueConstraint('event_id', name=op.f('investigation_events_event_id_key')),
    sa.UniqueConstraint('job_id', 'attempt_id', 'kind', name='uq_investigation_attempt_kind'),
    schema=SCHEMA
    )
    op.create_index(op.f('research_local_investigation_events_job_id_idx'), 'investigation_events', ['job_id'], unique=False,
                    schema=SCHEMA)
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
    schema=SCHEMA
    )
    op.create_table('investigation_reports',
    sa.Column('report_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('declaration_id', sa.UUID(), nullable=False),
    sa.Column('dataset_id', sa.UUID(), nullable=False),
    sa.Column('content_sha256', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('report_id', name=op.f('investigation_reports_pkey')),
    sa.UniqueConstraint('job_id', name=op.f('investigation_reports_job_id_key')),
    schema=SCHEMA
    )
    for table in IMMUTABLE:
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {SCHEMA}.{table} "
                   "FOR EACH ROW EXECUTE FUNCTION public.edge_os_reject_change()")


def downgrade() -> None:
    for table in IMMUTABLE:
        op.execute(f"DROP TRIGGER {table}_immutable ON {SCHEMA}.{table}")
    op.drop_table('investigation_reports', schema=SCHEMA)
    op.drop_table('research_budgets', schema=SCHEMA)
    op.drop_index(op.f('research_local_investigation_events_job_id_idx'), table_name='investigation_events', schema=SCHEMA)
    op.drop_table('investigation_events', schema=SCHEMA)
    op.drop_table('investigation_jobs', schema=SCHEMA)
    op.drop_index(op.f('research_local_history_datasets_owner_id_idx'), table_name='history_datasets', schema=SCHEMA)
    op.drop_table('history_datasets', schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} RESTRICT")
