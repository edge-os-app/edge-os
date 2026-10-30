"""OWNER-TRIGGER-L3: the saved decision basis for the one owner-triggered in-app action.

Revision ID: 0014
Revises: 0013

`execution_decisions.decision_basis` records whether a decision came from the strategy rules (`RULE`, every
existing row and every other job) or from the one owner-triggered action (`OWNER_TRIGGER`). A partial unique
index allows only one owner-triggered decision per owner, agent, wallet and network, so a second action under the
same permission cannot create a second decision. Existing rows keep `RULE`. No other table changes.
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

SCHEMA = "execution_local"


def upgrade() -> None:
    op.add_column('execution_decisions',
                  sa.Column('decision_basis', sa.Text(), server_default=sa.text("'RULE'"), nullable=False),
                  schema=SCHEMA)
    op.create_check_constraint(op.f('execution_decisions_ck_execution_decisions_basis_check'), 'execution_decisions',
                               "decision_basis IN ('RULE','OWNER_TRIGGER')", schema=SCHEMA)
    op.create_index('uq_execution_decisions_owner_trigger', 'execution_decisions',
                    ['owner_id', 'agent_id', 'wallet_id', 'network_id'], unique=True, schema=SCHEMA,
                    postgresql_where=sa.text("decision_basis = 'OWNER_TRIGGER'"))


def downgrade() -> None:
    op.drop_index('uq_execution_decisions_owner_trigger', table_name='execution_decisions', schema=SCHEMA,
                  postgresql_where=sa.text("decision_basis = 'OWNER_TRIGGER'"))
    op.drop_constraint(op.f('execution_decisions_ck_execution_decisions_basis_check'), 'execution_decisions',
                       schema=SCHEMA, type_='check')
    op.drop_column('execution_decisions', 'decision_basis', schema=SCHEMA)
