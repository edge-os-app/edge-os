import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from edge_os_api.records.models import Base
from edge_os_api.wallet_setup.persistence import WALLET_SETUP_METADATA

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The wallet-setup package keeps its own metadata; migration 0007 creates those tables. Alembic
# compares against every metadata here so `alembic check` agrees with the migrated database.
target_metadata = [Base.metadata, WALLET_SETUP_METADATA]


def database_url() -> str:
    url = os.environ.get("EDGE_OS_DATABASE_URL")
    if not url:
        sys.exit("EDGE_OS_DATABASE_URL is required to run migrations")
    return url


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
