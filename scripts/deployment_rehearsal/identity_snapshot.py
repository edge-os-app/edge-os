"""Saved identities of one rehearsal database, read with direct SQL, and an exact before/after comparison.

A snapshot holds the schema head, a row count and content hash for every table in the owned schemas (`public` and
each `*_local` schema), and readable named identities: owners, saved requests, revisions, reports, replays,
recurring deployments, investigation jobs, usage caps, reservations and held unknown liability.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

TABLES_SQL = ("select table_schema || '.' || table_name as name from information_schema.tables "
              "where table_type = 'BASE TABLE' and (table_schema = 'public' or table_schema like '%\\_local') "
              "order by 1")
NAMED: dict[str, str] = {
    "owners": "select id::text from users order by id",
    "requests": "select record_id::text, record_type, md5(content::text) from records order by seq",
    "revisions": "select revision_id::text, strategy_id, content_sha256 from strategy_revisions order by created_at, revision_id",
    "reports": ("select report_id::text, job_id::text, content_sha256 from research_local.investigation_reports "
                "order by report_id"),
    "replays": "select replay_id::text, content_sha256 from spot_replay_runs order by replay_id",
    "deployments": ("select deployment_id::text, agent_id, state, consent_hash, occurrences, missed_slots "
                    "from execution_local.execution_recurring_deployments order by deployment_id"),
    "jobs": ("select job_id::text, kind, state, terminal_reason from research_local.investigation_jobs "
             "order by created_at, job_id"),
    "caps": ("select scope, owner_key::text, resource, cap, reserved, consumed, unknown, overrun "
             "from usage_local.usage_allocations order by scope, owner_key, resource"),
    "reservations": ("select reservation_id::text, subject_kind, subject_id, amounts, settled "
                     "from usage_local.usage_reservations order by reservation_id"),
    "held_unknown": ("select job_id::text, budget->'unknown_liability' from research_local.investigation_jobs j "
                     "where exists (select 1 from jsonb_each_text(coalesce(j.budget->'unknown_liability', '{}'::jsonb)) e "
                     "where e.value ~ '^[0-9.]+$' and e.value::numeric > 0) order by job_id"),
}


def _quoted(name: str) -> str:
    schema, table = name.split(".", 1)
    return '"' + schema.replace('"', '""') + '"."' + table.replace('"', '""') + '"'


def table_hash_sql(tables: list[str]) -> str:
    parts = [f"select '{name}' as name, count(*) as rows, md5(coalesce(string_agg(t::text, E'\\n' order by t::text), '')) "
             f"as md5 from {_quoted(name)} t" for name in tables]
    return " union all ".join(parts)


def take(rows: Callable[[str], list[dict[str, Any]]]) -> dict[str, Any]:
    """`rows(sql)` runs one query against the rehearsal database and returns its rows as dictionaries."""
    head = rows("select version_num from alembic_version")
    tables = [row["name"] for row in rows(TABLES_SQL)]
    hashed = {row["name"]: {"rows": row["rows"], "md5": row["md5"]} for row in rows(table_hash_sql(tables))}
    named = {key: [list(row.values()) for row in rows(sql)] for key, sql in NAMED.items()}
    return {"schema_head": [row["version_num"] for row in head], "tables": hashed, "named": named}


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict) and value and prefix.count(".") < 2:
        for key, item in value.items():
            _flatten(f"{prefix}.{key}" if prefix else key, item, out)
    else:
        out[prefix] = value


def differences(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Every path whose value changed, disappeared or appeared. An empty list means identical snapshots."""
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    _flatten("", before, old)
    _flatten("", after, new)
    found: list[str] = []
    for key in sorted(old.keys() | new.keys()):
        if key not in new:
            found.append(f"{key}: missing after")
        elif key not in old:
            found.append(f"{key}: added after")
        elif old[key] != new[key]:
            if isinstance(old[key], dict) and isinstance(new[key], dict):
                found += [f"{key}.{field}: {old[key].get(field)!r} -> {new[key].get(field)!r}"
                          for field in sorted(old[key].keys() | new[key].keys()) if old[key].get(field) != new[key].get(field)]
            else:
                found.append(f"{key}: {old[key]!r} -> {new[key]!r}")
    return found
