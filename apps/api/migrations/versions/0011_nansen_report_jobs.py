"""#58 RESEARCH-PORTS-LOCAL: Nansen report jobs on the existing investigation job table.

Revision ID: 0011
Revises: 0010

`investigation_jobs.kind` names the job's tool chain; every existing row is `HISTORY_INVESTIGATION`. A Nansen report
job is the same original job row with `kind = NANSEN_REPORT`; its `declaration_id` is the saved `nansen_requests` row
(one per owner, request and request key). `nansen_reports` keeps the frozen request, evidence and report packages with
their hashes. Requests and reports reject any update or delete. No existing key or saved row changes.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

SCHEMA = "research_local"
IMMUTABLE = ("nansen_requests", "nansen_reports")


def upgrade() -> None:
    op.add_column('investigation_jobs', sa.Column('kind', sa.Text(), server_default=sa.text("'HISTORY_INVESTIGATION'"),
                                                  nullable=False), schema=SCHEMA)
    op.create_check_constraint(op.f('investigation_jobs_kind_check'), 'investigation_jobs',
                               "kind IN ('HISTORY_INVESTIGATION', 'NANSEN_REPORT')", schema=SCHEMA)
    op.create_table('nansen_requests',
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('intake_record_id', sa.UUID(), nullable=False),
    sa.Column('request_key', sa.Text(), nullable=False),
    sa.Column('content_sha256', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name=op.f('nansen_requests_hash_check')),
    sa.PrimaryKeyConstraint('request_id', name=op.f('nansen_requests_pkey')),
    sa.UniqueConstraint('owner_id', 'intake_record_id', 'request_key', name='uq_nansen_request_key'),
    schema=SCHEMA
    )
    op.create_table('nansen_reports',
    sa.Column('report_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('content_sha256', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name=op.f('nansen_reports_hash_check')),
    sa.PrimaryKeyConstraint('report_id', name=op.f('nansen_reports_pkey')),
    sa.UniqueConstraint('job_id', name=op.f('nansen_reports_job_id_key')),
    schema=SCHEMA
    )
    for table in IMMUTABLE:
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {SCHEMA}.{table} "
                   "FOR EACH ROW EXECUTE FUNCTION public.edge_os_reject_change()")


def downgrade() -> None:
    for table in IMMUTABLE:
        op.execute(f"DROP TRIGGER {table}_immutable ON {SCHEMA}.{table}")
    op.drop_table('nansen_reports', schema=SCHEMA)
    op.drop_table('nansen_requests', schema=SCHEMA)
    op.drop_constraint(op.f('investigation_jobs_kind_check'), 'investigation_jobs', schema=SCHEMA, type_='check')
    op.drop_column('investigation_jobs', 'kind', schema=SCHEMA)
