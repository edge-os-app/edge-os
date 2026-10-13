"""P27 LOCAL: recurring deployments and saved evaluation outcomes on the existing job engine.

Revision ID: 0012
Revises: 0011

`execution_recurring_deployments` holds one explicit recurring authorization per adopted consent, with the
producer's slot cursor and missed-slot record. `execution_evaluation_outcomes` saves every evaluation outcome
(SIGNAL, NO_SIGNAL, INELIGIBLE or UNAVAILABLE) with its input and evaluation times before any intent.
`execution_evaluation_jobs.deployment_id` links an occurrence to its deployment; existing jobs keep NULL. No
existing row changes. The downgrade refuses while any deployment exists, because it would lose durable recurring work
and its occurrence lineage. Without deployments, a downgrade drops the saved outcome rows of manual evaluations
(their input and evaluation times); each job keeps its own outcome and reason, and no liability is held there.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

SCHEMA = "execution_local"


def upgrade() -> None:
    op.add_column('execution_evaluation_jobs', sa.Column('deployment_id', sa.UUID(), nullable=True), schema=SCHEMA)
    op.create_index('ix_execution_jobs_deployment', 'execution_evaluation_jobs', ['deployment_id', 'decision_slot'],
                    unique=False, schema=SCHEMA)
    op.create_table('execution_evaluation_outcomes',
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('deployment_id', sa.UUID(), nullable=True),
    sa.Column('decision_slot', sa.DateTime(timezone=True), nullable=False),
    sa.Column('outcome', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('decision_id', sa.UUID(), nullable=True),
    sa.Column('inputs_observed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('inputs_collected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("(outcome = 'UNAVAILABLE') = (decision_id IS NULL)",
                       name=op.f('execution_evaluation_outcomes_decision_presence_check')),
    sa.CheckConstraint("outcome IN ('SIGNAL','NO_SIGNAL','INELIGIBLE','UNAVAILABLE')",
                       name=op.f('execution_evaluation_outcomes_outcome_check')),
    sa.PrimaryKeyConstraint('job_id', name=op.f('execution_evaluation_outcomes_pkey')),
    schema=SCHEMA
    )
    op.create_index('ix_execution_outcomes_owner_agent', 'execution_evaluation_outcomes',
                    ['owner_id', 'agent_id', 'decision_slot'], unique=False, schema=SCHEMA)
    op.create_table('execution_recurring_deployments',
    sa.Column('deployment_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('request_key', sa.Text(), nullable=False),
    sa.Column('strategy_id', sa.Text(), nullable=False),
    sa.Column('publication_revision_id', sa.UUID(), nullable=False),
    sa.Column('execution_revision_id', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.Text(), nullable=False),
    sa.Column('manifest_hash', sa.Text(), nullable=False),
    sa.Column('consent_adoption_id', sa.UUID(), nullable=False),
    sa.Column('consent_hash', sa.Text(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('end_reason', sa.Text(), nullable=True),
    sa.Column('cursor_slot', sa.DateTime(timezone=True), nullable=True),
    sa.Column('occurrences', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('missed_slots', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('missed_intervals', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('last_tick_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("(state = 'ENDED') = (end_reason IS NOT NULL AND ended_at IS NOT NULL)",
                       name=op.f('execution_recurring_deployments_ended_check')),
    sa.CheckConstraint("length(request_key) BETWEEN 1 AND 200",
                       name=op.f('execution_recurring_deployments_request_key_check')),
    sa.CheckConstraint("missed_slots >= 0 AND occurrences >= 0",
                       name=op.f('execution_recurring_deployments_counts_check')),
    sa.CheckConstraint("state IN ('ACTIVE','ENDED')", name=op.f('execution_recurring_deployments_state_check')),
    sa.PrimaryKeyConstraint('deployment_id', name=op.f('execution_recurring_deployments_pkey')),
    sa.UniqueConstraint('owner_id', 'agent_id', 'request_key', name='uq_recurring_deployments_owner_agent_request'),
    sa.UniqueConstraint('owner_id', 'consent_adoption_id', name='uq_recurring_deployments_owner_consent'),
    schema=SCHEMA
    )
    op.create_index('ix_recurring_deployments_state', 'execution_recurring_deployments',
                    ['state', 'deployment_id'], unique=False, schema=SCHEMA)
    op.create_index('uq_recurring_deployments_active_wallet', 'execution_recurring_deployments',
                    ['owner_id', 'agent_id', 'wallet_id', 'network_id'], unique=True, schema=SCHEMA,
                    postgresql_where=sa.text("state = 'ACTIVE'"))


def downgrade() -> None:
    # Revision 0011 cannot hold a deployment or its occurrence lineage. Refuse instead of dropping them.
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM {SCHEMA}.execution_recurring_deployments) THEN
                RAISE EXCEPTION 'downgrade below 0012 refused: recurring deployments exist';
            END IF;
        END $$""")
    op.drop_index('uq_recurring_deployments_active_wallet', table_name='execution_recurring_deployments',
                  schema=SCHEMA, postgresql_where=sa.text("state = 'ACTIVE'"))
    op.drop_index('ix_recurring_deployments_state', table_name='execution_recurring_deployments', schema=SCHEMA)
    op.drop_table('execution_recurring_deployments', schema=SCHEMA)
    op.drop_index('ix_execution_outcomes_owner_agent', table_name='execution_evaluation_outcomes', schema=SCHEMA)
    op.drop_table('execution_evaluation_outcomes', schema=SCHEMA)
    op.drop_index('ix_execution_jobs_deployment', table_name='execution_evaluation_jobs', schema=SCHEMA)
    op.drop_column('execution_evaluation_jobs', 'deployment_id', schema=SCHEMA)
