"""#58 Stage 1 financial state: funding, admission, execution, recovery, stops, consent and removal tables.

Revision ID: 0008
Revises: 0007

Each accepted financial package keeps its own metadata in its own `*_local` schema. Earlier stages created
those tables only in test harnesses. This forward migration ships the same schemas, tables, constraints and
indexes through the normal additive path, so a fresh or upgraded database holds the accepted financial state
without `create_all`. No existing table, key, precision or saved row changes. `owner_id` columns follow the
verified `users.id` by application convention without a foreign key, matching the accepted packages.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


FINANCIAL_SCHEMAS = ("funding_local", "admission_local", "execution_local", "recovery_local", "stops_local",
                     "consent_local", "revocation_local")


def upgrade() -> None:
    for schema in FINANCIAL_SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.create_table('funding_credits',
    sa.Column('credit_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Text(), nullable=False),
    sa.Column('actual_raw', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.Column('decimals', sa.Integer(), nullable=False),
    sa.Column('fee_raw', sa.Numeric(precision=78, scale=0), nullable=True),
    sa.Column('fee_decimals', sa.Integer(), nullable=True),
    sa.Column('fee_asset_id', sa.Text(), nullable=True),
    sa.Column('event_id', sa.Text(), nullable=False),
    sa.Column('flow_id', sa.UUID(), nullable=False),
    sa.Column('observation_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('network_id IN (143, 10143)', name=op.f('funding_credits_network_check')),
    sa.PrimaryKeyConstraint('credit_id', name=op.f('funding_credits_pkey')),
    sa.UniqueConstraint('wallet_id', 'network_id', 'asset_id', 'event_id', name='uq_funding_credit_event_identity'),
    schema='funding_local'
    )
    op.create_index('ix_funding_credits_owner_wallet_asset', 'funding_credits', ['owner_id', 'wallet_id', 'asset_id'], unique=False, schema='funding_local')
    op.create_table('funding_denials',
    sa.Column('denial_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=True),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('denial_id', name=op.f('funding_denials_pkey')),
    schema='funding_local'
    )
    op.create_index('ix_funding_denials_owner_created', 'funding_denials', ['owner_id', 'created_at'], unique=False, schema='funding_local')
    op.create_table('funding_flows',
    sa.Column('flow_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('asset_id', sa.Text(), nullable=False),
    sa.Column('declared_raw', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.Column('decimals', sa.Integer(), nullable=False),
    sa.Column('declared_fee_raw', sa.Numeric(precision=78, scale=0), nullable=True),
    sa.Column('declared_fee_decimals', sa.Integer(), nullable=True),
    sa.Column('declared_fee_asset_id', sa.Text(), nullable=True),
    sa.Column('transport', sa.Text(), nullable=False),
    sa.Column('sender', sa.Text(), nullable=True),
    sa.Column('recipient', sa.Text(), nullable=True),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('reference', sa.Text(), nullable=False),
    sa.Column('transaction_reference', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('DEPOSIT', 'WITHDRAWAL')", name=op.f('funding_flows_kind_check')),
    sa.CheckConstraint("state IN ('PENDING', 'CONFIRMED', 'FAILED', 'UNKNOWN')", name=op.f('funding_flows_state_check')),
    sa.CheckConstraint('network_id IN (143, 10143)', name=op.f('funding_flows_network_check')),
    sa.PrimaryKeyConstraint('flow_id', name=op.f('funding_flows_pkey')),
    sa.UniqueConstraint('owner_id', 'agent_id', 'reference', name='uq_funding_flows_owner_agent_reference'),
    schema='funding_local'
    )
    op.create_index('ix_funding_flows_owner_wallet_state', 'funding_flows', ['owner_id', 'wallet_id', 'state'], unique=False, schema='funding_local')
    op.create_table('funding_observations',
    sa.Column('observation_id', sa.UUID(), nullable=False),
    sa.Column('sequence', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('flow_id', sa.UUID(), nullable=True),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Text(), nullable=True),
    sa.Column('actual_raw', sa.Numeric(precision=78, scale=0), nullable=True),
    sa.Column('decimals', sa.Integer(), nullable=True),
    sa.Column('fee_raw', sa.Numeric(precision=78, scale=0), nullable=True),
    sa.Column('fee_decimals', sa.Integer(), nullable=True),
    sa.Column('fee_asset_id', sa.Text(), nullable=True),
    sa.Column('event_id', sa.Text(), nullable=True),
    sa.Column('transaction_reference', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('sender', sa.Text(), nullable=True),
    sa.Column('recipient', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'CONFIRMED', 'FAILED', 'UNKNOWN', 'DUPLICATE')", name=op.f('funding_observations_status_check')),
    sa.PrimaryKeyConstraint('observation_id', name=op.f('funding_observations_pkey')),
    sa.UniqueConstraint('sequence', name=op.f('funding_observations_sequence_key')),
    schema='funding_local'
    )
    op.create_index('ix_funding_observations_flow', 'funding_observations', ['flow_id', 'sequence'], unique=False, schema='funding_local')
    op.create_index('ix_funding_observations_owner_wallet_sequence', 'funding_observations', ['owner_id', 'wallet_id', 'sequence'], unique=False, schema='funding_local')
    op.create_table('funding_profiles',
    sa.Column('profile_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Integer(), nullable=False),
    sa.Column('trading_asset_id', sa.Text(), nullable=False),
    sa.Column('trading_decimals', sa.Integer(), nullable=False),
    sa.Column('gas_asset_id', sa.Text(), nullable=False),
    sa.Column('gas_decimals', sa.Integer(), nullable=False),
    sa.Column('compute_asset_id', sa.Text(), nullable=True),
    sa.Column('compute_decimals', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('network_id IN (143, 10143)', name=op.f('funding_profiles_network_check')),
    sa.PrimaryKeyConstraint('profile_id', name=op.f('funding_profiles_pkey')),
    sa.UniqueConstraint('owner_id', 'agent_id', name='uq_funding_profiles_owner_agent'),
    schema='funding_local'
    )
    op.create_table('admission_allowances',
    sa.Column('allowance_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('asset_id', sa.Text(), nullable=False),
    sa.Column('decimals', sa.BigInteger(), nullable=False),
    sa.Column('approval_id', sa.Text(), nullable=False),
    sa.Column('approval_hash', sa.Text(), nullable=False),
    sa.Column('approved', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.Column('consumed', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.CheckConstraint('approved >= 0 AND consumed >= 0', name=op.f('admission_allowances_ck_admission_allowances_non_negative_check')),
    sa.PrimaryKeyConstraint('allowance_id', name=op.f('admission_allowances_pkey')),
    sa.UniqueConstraint('owner_id', 'agent_id', 'wallet_id', 'network_id', 'asset_id', name='uq_admission_allowances_key'),
    schema='admission_local'
    )
    op.create_table('admission_decisions',
    sa.Column('decision_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('review_hash', sa.Text(), nullable=False),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('binding', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PROPOSED','ADMITTED','DENIED','CANCELLED','CONFIRMED','REVERTED','SUBMISSION_UNKNOWN','BREACHED')", name=op.f('admission_decisions_ck_admission_decisions_status_check')),
    sa.PrimaryKeyConstraint('decision_id', name=op.f('admission_decisions_pkey')),
    sa.UniqueConstraint('owner_id', 'action_id', name='uq_admission_decisions_owner_action'),
    schema='admission_local'
    )
    op.create_index('ix_admission_decisions_owner_agent', 'admission_decisions', ['owner_id', 'agent_id'], unique=False, schema='admission_local')
    op.create_index('ix_admission_decisions_owner_wallet', 'admission_decisions', ['owner_id', 'wallet_id', 'network_id'], unique=False, schema='admission_local')
    op.create_table('admission_positions',
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('position_id', sa.Text(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('strategy_revision', sa.Text(), nullable=False),
    sa.Column('mandate_id', sa.Text(), nullable=False),
    sa.Column('asset_id', sa.Text(), nullable=False),
    sa.Column('decimals', sa.BigInteger(), nullable=False),
    sa.Column('quote_asset_id', sa.Text(), nullable=False),
    sa.Column('quote_decimals', sa.BigInteger(), nullable=False),
    sa.Column('inventory', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.Column('cost_basis', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.Column('realized_quote', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.CheckConstraint('inventory >= 0 AND cost_basis >= 0', name=op.f('admission_positions_ck_admission_positions_non_negative_check')),
    sa.PrimaryKeyConstraint('owner_id', 'position_id', name='pk_admission_positions'),
    schema='admission_local'
    )
    op.create_table('admission_receipts',
    sa.Column('receipt_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('position_id', sa.Text(), server_default='', nullable=False),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('review_hash', sa.Text(), nullable=False),
    sa.Column('outcome', sa.Text(), nullable=False),
    sa.Column('breach', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('receipt_id', name=op.f('admission_receipts_pkey')),
    schema='admission_local'
    )
    op.create_index('ix_admission_receipts_owner_action', 'admission_receipts', ['owner_id', 'action_id', 'created_at'], unique=False, schema='admission_local')
    op.create_index('ix_admission_receipts_owner_wallet', 'admission_receipts', ['owner_id', 'wallet_id', 'network_id'], unique=False, schema='admission_local')
    op.create_table('admission_reservations',
    sa.Column('reservation_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('review_hash', sa.Text(), nullable=False),
    sa.Column('scope', sa.Text(), nullable=False),
    sa.Column('position_id', sa.Text(), server_default='', nullable=False),
    sa.Column('asset_id', sa.Text(), nullable=False),
    sa.Column('decimals', sa.BigInteger(), nullable=False),
    sa.Column('raw', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('reconciled_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("state IN ('RESERVED','CONSUMED','RELEASED')", name=op.f('admission_reservations_ck_admission_reservations_state_check')),
    sa.CheckConstraint('raw >= 0', name=op.f('admission_reservations_ck_admission_reservations_non_negative_check')),
    sa.PrimaryKeyConstraint('reservation_id', name=op.f('admission_reservations_pkey')),
    sa.UniqueConstraint('owner_id', 'action_id', 'scope', 'asset_id', 'position_id', name='uq_admission_reservations_atom'),
    schema='admission_local'
    )
    op.create_index('ix_admission_reservations_owner_position', 'admission_reservations', ['owner_id', 'position_id', 'state'], unique=False, schema='admission_local')
    op.create_index('ix_admission_reservations_owner_wallet_state', 'admission_reservations', ['owner_id', 'wallet_id', 'network_id', 'asset_id', 'state'], unique=False, schema='admission_local')
    op.create_table('execution_claims',
    sa.Column('claim_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('queue_id', sa.UUID(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('acquired_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("state IN ('ACTIVE','RELEASED')", name=op.f('execution_claims_ck_execution_claims_state_check')),
    sa.PrimaryKeyConstraint('claim_id', name=op.f('execution_claims_pkey')),
    schema='execution_local'
    )
    op.create_index('uq_execution_claims_active_wallet', 'execution_claims', ['owner_id', 'agent_id', 'wallet_id', 'network_id'], unique=True, schema='execution_local', postgresql_where=sa.text('released_at IS NULL'))
    op.create_table('execution_decisions',
    sa.Column('decision_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('strategy_id', sa.Text(), nullable=False),
    sa.Column('revision_id', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.Text(), nullable=False),
    sa.Column('manifest_hash', sa.Text(), nullable=False),
    sa.Column('market_binding_id', sa.Text(), nullable=False),
    sa.Column('decision_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('operation', sa.Text(), nullable=True),
    sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rule_results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('inputs_hash', sa.Text(), nullable=False),
    sa.Column('inputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('SIGNAL','NO_SIGNAL','INELIGIBLE')", name=op.f('execution_decisions_ck_execution_decisions_status_check')),
    sa.PrimaryKeyConstraint('decision_id', name=op.f('execution_decisions_pkey')),
    sa.UniqueConstraint('owner_id', 'decision_id', name='uq_execution_decisions_owner_decision'),
    schema='execution_local'
    )
    op.create_index('ix_execution_decisions_owner_revision', 'execution_decisions', ['owner_id', 'revision_id'], unique=False, schema='execution_local')
    op.create_index('ix_execution_decisions_owner_wallet', 'execution_decisions', ['owner_id', 'wallet_id', 'network_id'], unique=False, schema='execution_local')
    op.create_table('execution_intents',
    sa.Column('intent_id', sa.Text(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('decision_id', sa.UUID(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('review_hash', sa.Text(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('position_id', sa.Text(), nullable=False),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('revision_id', sa.Text(), nullable=False),
    sa.Column('mandate_id', sa.Text(), nullable=False),
    sa.Column('policy_binding', sa.Text(), nullable=False),
    sa.Column('payload_hash', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('admission_status', sa.Text(), nullable=False),
    sa.Column('admission_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("operation IN ('ENTRY','EXIT')", name=op.f('execution_intents_ck_execution_intents_operation_check')),
    sa.PrimaryKeyConstraint('intent_id', name=op.f('execution_intents_pkey')),
    sa.UniqueConstraint('owner_id', 'action_id', name='uq_execution_intents_owner_action'),
    sa.UniqueConstraint('owner_id', 'intent_id', name='uq_execution_intents_owner_intent'),
    schema='execution_local'
    )
    op.create_index('ix_execution_intents_owner_decision', 'execution_intents', ['owner_id', 'decision_id'], unique=False, schema='execution_local')
    op.create_table('execution_queue',
    sa.Column('queue_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('intent_id', sa.Text(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('decision_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('position_id', sa.Text(), nullable=False),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('priority', sa.BigInteger(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('blocking_reason', sa.Text(), nullable=True),
    sa.Column('revalidation', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('enqueued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("state IN ('QUEUED','CLAIMED','REVALIDATION_DENIED','ADMISSION_DENIED','BREACHED','RECONCILE_MISMATCH','SUBMISSION_NOT_OWNED','SUBMITTED_CONFIRMED','SUBMITTED_REVERTED','SUBMITTED_UNKNOWN','DENIED_UNSENT')", name=op.f('execution_queue_ck_execution_queue_state_check')),
    sa.PrimaryKeyConstraint('queue_id', name=op.f('execution_queue_pkey')),
    sa.UniqueConstraint('owner_id', 'action_id', name='uq_execution_queue_owner_action'),
    schema='execution_local'
    )
    op.create_index('ix_execution_queue_owner_order', 'execution_queue', ['owner_id', 'priority', 'enqueued_at', 'queue_id'], unique=False, schema='execution_local')
    op.create_index('ix_execution_queue_owner_wallet_state', 'execution_queue', ['owner_id', 'wallet_id', 'network_id', 'state'], unique=False, schema='execution_local')
    op.create_table('execution_submission_attempts',
    sa.Column('attempt_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('queue_id', sa.UUID(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('transport_id', sa.Text(), nullable=False),
    sa.Column('payload_hash', sa.Text(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('outcome', sa.Text(), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("outcome IS NULL OR outcome IN ('DEFINITELY_UNSENT','SUBMISSION_POSSIBLE','CONFIRMED','REVERTED')", name=op.f('execution_submission_attempts_ck_execution_attempts_outcome_check')),
    sa.CheckConstraint("state IN ('IN_FLIGHT','TERMINAL')", name=op.f('execution_submission_attempts_ck_execution_attempts_state_check')),
    sa.PrimaryKeyConstraint('attempt_id', name=op.f('execution_submission_attempts_pkey')),
    schema='execution_local'
    )
    op.create_index('ix_execution_attempts_owner_action', 'execution_submission_attempts', ['owner_id', 'action_id'], unique=False, schema='execution_local')
    op.create_index('ix_execution_attempts_owner_wallet', 'execution_submission_attempts', ['owner_id', 'wallet_id', 'network_id', 'started_at'], unique=False, schema='execution_local')
    op.create_table('recovery_cases',
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('revision_id', sa.Text(), nullable=False),
    sa.Column('policy_binding', sa.Text(), nullable=False),
    sa.Column('payload_hash', sa.Text(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('blocking_reason', sa.Text(), nullable=True),
    sa.Column('decision_status', sa.Text(), nullable=False),
    sa.Column('queue_state', sa.Text(), nullable=True),
    sa.Column('claim_held', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('delayed_exit', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('reconciled_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("state IN ('OPEN','CONFIRMED','REVERTED','DENIED_UNSENT','UNKNOWN','BREACHED','RECONCILE_MISMATCH','DISCREPANCY','NO_ADMISSION_DECISION','NO_SUBMISSION_ATTEMPT')", name=op.f('recovery_cases_ck_recovery_cases_state_check')),
    sa.PrimaryKeyConstraint('case_id', name=op.f('recovery_cases_pkey')),
    sa.UniqueConstraint('owner_id', 'action_id', name='uq_recovery_cases_owner_action'),
    schema='recovery_local'
    )
    op.create_index('ix_recovery_cases_owner_wallet', 'recovery_cases', ['owner_id', 'wallet_id', 'network_id'], unique=False, schema='recovery_local')
    op.create_table('recovery_evidence',
    sa.Column('evidence_id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('action_id', sa.Text(), nullable=False),
    sa.Column('fingerprint', sa.Text(), nullable=False),
    sa.Column('outcome', sa.Text(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('source_ref', sa.Text(), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("state IN ('PENDING','ACCEPTED','REJECTED')", name=op.f('recovery_evidence_ck_recovery_evidence_state_check')),
    sa.PrimaryKeyConstraint('evidence_id', name=op.f('recovery_evidence_pkey')),
    sa.UniqueConstraint('owner_id', 'action_id', 'fingerprint', name='uq_recovery_evidence_fingerprint'),
    schema='recovery_local'
    )
    op.create_index('ix_recovery_evidence_owner_action', 'recovery_evidence', ['owner_id', 'action_id', 'created_at'], unique=False, schema='recovery_local')
    op.create_table('scoped_stops',
    sa.Column('stop_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('scope', sa.Text(), nullable=False),
    sa.Column('mode', sa.Text(), nullable=False),
    sa.Column('trigger', sa.Text(), nullable=False),
    sa.Column('position_id', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("mode IN ('STOP_NEW_ENTRIES','HALT_ALL_SWAPS')", name=op.f('scoped_stops_ck_scoped_stops_mode_check')),
    sa.CheckConstraint("scope IN ('POSITION','AGENT_WALLET_NETWORK')", name=op.f('scoped_stops_ck_scoped_stops_scope_check')),
    sa.CheckConstraint("trigger IN ('USER','TRIAL','POSITION_LOSS','WALLET_LOSS')", name=op.f('scoped_stops_ck_scoped_stops_trigger_check')),
    sa.PrimaryKeyConstraint('stop_id', name=op.f('scoped_stops_pkey')),
    sa.UniqueConstraint('owner_id', 'agent_id', 'wallet_id', 'network_id', 'scope', 'position_id', 'mode', 'trigger', name='uq_scoped_stops_identity'),
    schema='stops_local'
    )
    op.create_index('ix_scoped_stops_owner_wallet', 'scoped_stops', ['owner_id', 'agent_id', 'wallet_id', 'network_id'], unique=False, schema='stops_local')
    op.create_table('consent_adoptions',
    sa.Column('adoption_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('review_id', sa.UUID(), nullable=False),
    sa.Column('review_hash', sa.Text(), nullable=False),
    sa.Column('consent_hash', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status = 'INACTIVE'", name=op.f('consent_adoptions_ck_consent_adoptions_status_check')),
    sa.PrimaryKeyConstraint('adoption_id', name=op.f('consent_adoptions_pkey')),
    sa.UniqueConstraint('owner_id', 'review_id', name='uq_consent_adoptions_owner_review'),
    schema='consent_local'
    )
    op.create_index('ix_consent_adoptions_owner_review', 'consent_adoptions', ['owner_id', 'review_id'], unique=False, schema='consent_local')
    op.create_table('consent_denials',
    sa.Column('denial_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=True),
    sa.Column('operation', sa.Text(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("operation IN ('REVIEW','ADOPT','READ')", name=op.f('consent_denials_ck_consent_denials_operation_check')),
    sa.PrimaryKeyConstraint('denial_id', name=op.f('consent_denials_pkey')),
    schema='consent_local'
    )
    op.create_index('ix_consent_denials_owner_operation', 'consent_denials', ['owner_id', 'operation', 'created_at'], unique=False, schema='consent_local')
    op.create_table('consent_reviews',
    sa.Column('review_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('strategy_id', sa.Text(), nullable=False),
    sa.Column('strategy_revision_id', sa.UUID(), nullable=False),
    sa.Column('content_sha256', sa.Text(), nullable=False),
    sa.Column('manifest_sha256', sa.Text(), nullable=False),
    sa.Column('terms_version', sa.Text(), nullable=False),
    sa.Column('terms_hash', sa.Text(), nullable=False),
    sa.Column('review_hash', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status = 'INACTIVE'", name=op.f('consent_reviews_ck_consent_reviews_status_check')),
    sa.PrimaryKeyConstraint('review_id', name=op.f('consent_reviews_pkey')),
    sa.UniqueConstraint('owner_id', 'agent_id', 'strategy_revision_id', name='uq_consent_reviews_identity'),
    sa.UniqueConstraint('owner_id', 'review_id', name='uq_consent_reviews_owner_review'),
    schema='consent_local'
    )
    op.create_index('ix_consent_reviews_owner_agent', 'consent_reviews', ['owner_id', 'agent_id'], unique=False, schema='consent_local')
    op.create_table('removal_observations',
    sa.Column('observation_id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('observation_key', sa.Text(), nullable=False),
    sa.Column('observed_state', sa.Text(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('signer_identity', sa.Text(), nullable=True),
    sa.Column('policy_identity', sa.Text(), nullable=True),
    sa.Column('matched', sa.Boolean(), nullable=False),
    sa.Column('contradictory', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('denial_code', sa.Text(), nullable=True),
    sa.Column('derived_state', sa.Text(), nullable=True),
    sa.Column('derived_reason', sa.Text(), nullable=True),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sequence', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("derived_state IS NULL OR derived_state IN ('NOT_REQUESTED', 'REQUESTED', 'PENDING', 'UNKNOWN', 'CONFIRMED', 'FAILED')", name=op.f('removal_observations_ck_removal_observations_derived_state_check')),
    sa.CheckConstraint("observed_state IN ('PENDING', 'UNKNOWN', 'CONFIRMED', 'FAILED')", name=op.f('removal_observations_ck_removal_observations_state_check')),
    sa.CheckConstraint('(matched AND denial_code IS NULL) OR (NOT matched AND denial_code IS NOT NULL)', name=op.f('removal_observations_ck_removal_observations_denial_check')),
    sa.PrimaryKeyConstraint('observation_id', name=op.f('removal_observations_pkey')),
    sa.UniqueConstraint('owner_id', 'observation_key', name='uq_removal_observations_owner_key'),
    sa.UniqueConstraint('sequence', name=op.f('removal_observations_sequence_key')),
    schema='revocation_local'
    )
    op.create_index('ix_removal_observations_request', 'removal_observations', ['request_id', 'sequence'], unique=False, schema='revocation_local')
    op.create_table('removal_requests',
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('request_key', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('signer_identity', sa.Text(), nullable=True),
    sa.Column('policy_identity', sa.Text(), nullable=True),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('request_id', name=op.f('removal_requests_pkey')),
    sa.UniqueConstraint('owner_id', 'agent_id', 'wallet_id', 'network_id', name='uq_removal_requests_identity'),
    sa.UniqueConstraint('owner_id', 'request_key', name='uq_removal_requests_owner_key'),
    schema='revocation_local'
    )
    op.create_index('ix_removal_requests_owner_wallet', 'removal_requests', ['owner_id', 'agent_id', 'wallet_id', 'network_id'], unique=False, schema='revocation_local')
    op.create_table('removal_states',
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.Text(), nullable=False),
    sa.Column('wallet_id', sa.Text(), nullable=False),
    sa.Column('network_id', sa.Text(), nullable=False),
    sa.Column('state', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('evidenced_signer', sa.Text(), nullable=True),
    sa.Column('evidenced_policy', sa.Text(), nullable=True),
    sa.Column('contradictory', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('last_observation_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("state IN ('NOT_REQUESTED', 'REQUESTED', 'PENDING', 'UNKNOWN', 'CONFIRMED', 'FAILED')", name=op.f('removal_states_ck_removal_states_state_check')),
    sa.PrimaryKeyConstraint('request_id', name=op.f('removal_states_pkey')),
    schema='revocation_local'
    )
    op.create_index('ix_removal_states_owner_wallet', 'removal_states', ['owner_id', 'agent_id', 'wallet_id', 'network_id'], unique=False, schema='revocation_local')


def downgrade() -> None:
    # Each schema holds only the tables this revision created, so dropping it removes exactly those tables.
    for schema in reversed(FINANCIAL_SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
