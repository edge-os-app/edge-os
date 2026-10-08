"""Engine, session factory and schema-revision checks."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

API_ROOT = Path(__file__).resolve().parents[2]


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10, pool_timeout=10,
                         hide_parameters=True,  # SQL errors must not write the user's saved words to the log
                         connect_args={"connect_timeout": 5})


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def script_head() -> str:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("no migration head found")
    return head


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


class SchemaMismatch(RuntimeError):
    pass


def require_head(engine: Engine) -> str:
    current, head = current_revision(engine), script_head()
    if current != head:
        raise SchemaMismatch(f"database schema revision {current!r} does not match migration head {head!r}; "
                             "run `alembic upgrade head` first")
    return head
