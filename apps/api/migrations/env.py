import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from edge_os_api.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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
