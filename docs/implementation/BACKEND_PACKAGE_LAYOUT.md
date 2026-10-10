# Backend package layout

The API package groups code by responsibility. It retains the existing HTTP routes, command-line entrypoint, record formats, schema revisions and calculation rules.

```text
apps/api/src/edge_os_api/
├── main.py                  application factory and route composition
├── __main__.py              python -m edge_os_api startup
├── core/
│   ├── authentication.py    verified principals and owner identity
│   ├── database.py          engine, sessions and schema readiness
│   ├── errors.py            sanitized HTTP error envelopes
│   ├── settings.py          typed startup configuration
│   └── request_schemas.py   shared strict request validation
├── records/
│   ├── contract_adapter.py  unchanged frozen P02 contract loading
│   └── models.py            shared append-only SQLAlchemy definitions
├── strategies/
│   └── compiler.py          P06 compilation and expression evaluation
├── research/
│   ├── fixture_interpreter.py    labelled scripted interpreter, no model call
│   ├── outcome_router.py         deterministic meaning and outcome routing
│   ├── service.py                owner-scoped saved Research workflow
│   ├── investigation_adoption.py immutable investigation review/adoption
│   ├── effect_comparison.py      pure descriptive comparison calculations
│   └── comparison_runs.py        adopted runs, attempts and saved reports
├── replay/
│   ├── simulator.py         deterministic adopted P12 replay calculations
│   └── saved_runs.py        owner-scoped run persistence and recovery
├── accounts/
│   └── views.py             persisted Agents, Positions and Funds reads
└── agent_context/
    └── controls.py          versioned adoption, correction, disable and clear
```

Package initializer files contain documentation only. Callers import the responsible module explicitly. There are no old-path wrapper modules or eager re-export chains. Request schemas and SQLAlchemy definitions remain shared because the existing record graph spans these domains. Moving them does not split tables or change their registration.

The old ticket-named application modules become records.contract_adapter and strategies.compiler. Versioned schema IDs, numerical contracts, migration IDs and protocol-specific function names remain unchanged. Compiler tests are named test_strategy_compiler.py and test_strategy_compilation_api.py.

Frozen contracts still load from docs/contracts in the repository. Synthetic fixtures still load from apps/api/tests/fixtures. A deployment must include those existing resources, not only the Python source package. All depth-sensitive paths account for the extra package directory, independent of the current working directory. Alembic imports the same Base and table definitions through records.models. No migration-version file changed.

## Development and verification

From apps/api, run uv sync --frozen, then uv run --frozen pytest. The package uses its pinned Python3.14 environment. Do not install application dependencies into an unrelated workspace interpreter.

The external entrypoint remains uvicorn edge_os_api.main:create_app --factory. python -m edge_os_api retains its configuration/readiness checks. Existing EDGE_OS settings, authorization, errors, retry behavior and database meanings remain unchanged.

tests/test_package_layout.py checks explicit domain imports, all11 existing metadata tables and frozen contract/fixture/profile/Alembic paths after changing the working directory. Existing behavioral tests remain the authority for API/calculation/storage behavior. The verify-edge-os skill and feature map retain the full actual authenticated browser/API/PostgreSQL/restart path.

This reorganization adds no live model, data, trading, wallet or funding capability. P07/P04/P16 qualification limits remain unchanged.
