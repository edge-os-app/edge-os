"""Private backup of the primary rehearsal database and its restore into a fresh, separately owned database.

The source database is only read (`pg_dump -Fc`). The restore target must be a different, run-named database that
holds no table yet; anything else is refused before `pg_restore` runs. Nothing is dropped, cleaned or overwritten.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from local_stack import LocalStack, text

RESTORE_NAME = re.compile(r"^edge_os_restore_[a-z0-9]{4,20}$")
EXISTING_TABLES_SQL = ("select coalesce(string_agg(table_schema || '.' || table_name, ',' order by 1), '') "
                       "from information_schema.tables where table_schema not in ('pg_catalog', 'information_schema')")


class RestoreRefused(RuntimeError):
    pass


def check_restore_target(name: str, *, source: str, existing_tables: list[str]) -> None:
    if name == source:
        raise RestoreRefused("the restore target is the source database")
    if not RESTORE_NAME.fullmatch(name):
        raise RestoreRefused(f"restore target name {name!r} is not a run-named restore database")
    if existing_tables:
        raise RestoreRefused(f"restore target {name} is not empty ({len(existing_tables)} tables)")


def backup(source: LocalStack, destination: Path) -> dict[str, object]:
    """Custom-format dump of the source database into a private file; returns its size, hash and table of contents."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "wb") as handle:
        result = source.compose("exec", "-T", "postgres", "pg_dump", "-U", "edge_os", "-d", source.names.database,
                                "-Fc", "--no-password", stdout=handle, check=False, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed with exit {result.returncode}")
    data = destination.read_bytes()
    listing = source.compose("exec", "-T", "postgres", "pg_restore", "--list", input_bytes=data, timeout=120)
    entries = [line for line in text(listing).splitlines() if line and not line.startswith(";")]
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "toc_entries": len(entries),
            "source_database": source.names.database}


def restore(target: LocalStack, dump: Path, *, source_database: str) -> dict[str, object]:
    existing = [item for item in target.psql(EXISTING_TABLES_SQL).split(",") if item]
    check_restore_target(target.names.database, source=source_database, existing_tables=existing)
    result = target.compose("exec", "-T", "postgres", "pg_restore", "-U", "edge_os", "-d", target.names.database,
                            "--exit-on-error", "--single-transaction", "--no-owner", "--role=edge_os",
                            input_bytes=dump.read_bytes(), check=False, timeout=300)
    target.log("pg-restore", result)
    if result.returncode != 0:
        raise RuntimeError(f"pg_restore failed with exit {result.returncode}")
    return {"target_database": target.names.database, "tables_before_restore": len(existing),
            "dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest()}
