import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from edge_os_api.admission.models import AdmissionBase
from edge_os_api.consent.records import ConsentBase
from edge_os_api.execution.models import ExecutionBase
from edge_os_api.funding.persistence import FundingBase
from edge_os_api.recovery.models import RecoveryBase
from edge_os_api.records.models import Base
from edge_os_api.research.history_dataset import ResearchBase
from edge_os_api.research import investigation_jobs  # noqa: F401 - registers the job tables on ResearchBase
from edge_os_api.revocation.records import RevocationBase
from edge_os_api.stops.models import StopBase
from edge_os_api.wallet_setup.persistence import WALLET_SETUP_METADATA

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The wallet-setup package keeps its own metadata; migration 0007 creates those tables. The financial
# packages keep their own metadata in their own `*_local` schemas; migration 0008 creates them. Alembic
# compares against every metadata here so `alembic check` agrees with the migrated database.
FINANCIAL_METADATA = [FundingBase.metadata, AdmissionBase.metadata, ExecutionBase.metadata, RecoveryBase.metadata,
                      StopBase.metadata, ConsentBase.metadata, RevocationBase.metadata]
# Migration 0009 creates the #58 research tables in `research_local`.
RESEARCH_METADATA = [ResearchBase.metadata]
target_metadata = [Base.metadata, WALLET_SETUP_METADATA, *FINANCIAL_METADATA, *RESEARCH_METADATA]
OWNED_SCHEMAS = {None, "public", *(metadata.schema for metadata in FINANCIAL_METADATA + RESEARCH_METADATA)}


def include_name(name, type_, parent_names):
    """Compare only the public schema and the owned financial schemas, never another schema in the database."""
    if type_ == "schema":
        return name in OWNED_SCHEMAS
    return True


def database_url() -> str:
    url = os.environ.get("EDGE_OS_DATABASE_URL")
    if not url:
        sys.exit("EDGE_OS_DATABASE_URL is required to run migrations")
    return url


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_schemas=True,
                          include_name=include_name)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
