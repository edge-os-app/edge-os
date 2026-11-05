"""ORBIO-ROUTE-L4: one spend ledger for every route.

Revision ID: 0015
Revises: 0014

`usage_local.provider_spend_route_prices` holds one frozen token price per route, as `route_id` text from the release
record, so a new provider needs no migration of a type. `provider_spend_reservations.route_id` saves each reservation's
route. The caps stay in the one settings row, and the cap check still sums every route.

The frozen settings price moves to the route `openrouter-openai-standard`, the only ACTUAL route before this revision,
and every existing reservation is labelled with it. No amount changes and no event is touched: the column is added with
a default, so no row is rewritten and `updated_at` keeps its value.

The downgrade moves one route's price back to the settings row. It refuses while the ledger holds another route, or a
settings row with no price, because revision 0014 cannot hold them.
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None

SCHEMA = "usage_local"
OPENROUTER_ROUTE = "openrouter-openai-standard"


def upgrade() -> None:
    op.create_table('provider_spend_route_prices',
    sa.Column('route_id', sa.Text(), nullable=False),
    sa.Column('prompt_usd_per_million', sa.Text(), nullable=False),
    sa.Column('completion_usd_per_million', sa.Text(), nullable=False),
    sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('route_id', name=op.f('provider_spend_route_prices_pkey')),
    schema=SCHEMA
    )
    op.execute(f"INSERT INTO {SCHEMA}.provider_spend_route_prices "
               f"SELECT '{OPENROUTER_ROUTE}', prompt_usd_per_million, completion_usd_per_million, frozen_at "
               f"FROM {SCHEMA}.provider_spend_settings")
    op.add_column('provider_spend_reservations',
                  sa.Column('route_id', sa.Text(), server_default=sa.text(f"'{OPENROUTER_ROUTE}'"), nullable=False),
                  schema=SCHEMA)
    op.alter_column('provider_spend_reservations', 'route_id', server_default=None, schema=SCHEMA)
    op.create_foreign_key(op.f('provider_spend_reservations_route_id_fkey'), 'provider_spend_reservations',
                          'provider_spend_route_prices', ['route_id'], ['route_id'], source_schema=SCHEMA,
                          referent_schema=SCHEMA)
    op.drop_column('provider_spend_settings', 'prompt_usd_per_million', schema=SCHEMA)
    op.drop_column('provider_spend_settings', 'completion_usd_per_million', schema=SCHEMA)


def downgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF (SELECT count(*) FROM {SCHEMA}.provider_spend_route_prices) > 1
                    OR (EXISTS (SELECT 1 FROM {SCHEMA}.provider_spend_settings)
                        AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.provider_spend_route_prices)) THEN
                RAISE EXCEPTION 'downgrade below 0015 refused: the spend ledger holds more than one route, or no price';
            END IF;
        END $$""")
    # Rebuilt, not altered: the 0014 ledger inserts by column position, so the price columns must return to their place.
    op.execute(f"CREATE TEMPORARY TABLE spend_settings_0015 ON COMMIT DROP AS SELECT s.settings_id, s.global_cap_nano_usd, "
               f"s.owner_cap_nano_usd, r.prompt_usd_per_million, r.completion_usd_per_million, s.cap_source, s.frozen_at, "
               f"s.updated_at FROM {SCHEMA}.provider_spend_settings s, {SCHEMA}.provider_spend_route_prices r")
    op.drop_table('provider_spend_settings', schema=SCHEMA)
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
    op.execute(f"INSERT INTO {SCHEMA}.provider_spend_settings SELECT * FROM spend_settings_0015")
    op.drop_constraint(op.f('provider_spend_reservations_route_id_fkey'), 'provider_spend_reservations',
                       type_='foreignkey', schema=SCHEMA)
    op.drop_column('provider_spend_reservations', 'route_id', schema=SCHEMA)
    op.drop_table('provider_spend_route_prices', schema=SCHEMA)
