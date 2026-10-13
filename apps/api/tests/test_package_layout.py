"""Public imports and frozen repository resources after domain organization."""

from importlib import import_module
from pathlib import Path

from pytest import MonkeyPatch


def test_domain_imports_and_shared_metadata() -> None:
    modules = (
        "core.authentication", "core.database", "core.errors", "core.settings",
        "core.request_schemas", "records.models", "records.contract_adapter",
        "strategies.compiler", "research.fixture_interpreter", "research.outcome_router",
        "research.service", "research.investigation_adoption", "research.effect_comparison",
        "research.comparison_runs", "research.hermes_interpreter", "research.interpretation_response",
        "research.interpretation_attempts", "replay.simulator", "replay.saved_runs",
        "accounts.views", "agent_context.controls", "wallet_setup.adapter", "wallet_setup.router",
    )
    for name in modules:
        import_module(f"edge_os_api.{name}")
    models = import_module("edge_os_api.records.models")
    assert set(models.Base.metadata.tables) == {
        "users", "records", "strategy_revisions", "idempotency_records",
        "investigation_declarations", "investigation_access_events",
        "effect_run_declarations", "effect_run_events", "effect_reports",
        "spot_replay_runs", "spot_replay_configurations",
        "interpretation_attempts", "interpretation_settlements", "interpretation_attempt_links",
        "interpretation_late_results",
    }


def test_resource_paths_are_independent_of_working_directory(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    repository = Path(__file__).resolve().parents[3]
    api_root = repository / "apps" / "api"
    monkeypatch.chdir(tmp_path)
    database = import_module("edge_os_api.core.database")
    records = import_module("edge_os_api.records.contract_adapter")
    compiler = import_module("edge_os_api.strategies.compiler")
    comparisons = import_module("edge_os_api.research.comparison_runs")
    replays = import_module("edge_os_api.replay.saved_runs")
    assert database.API_ROOT == api_root
    assert database.script_head() == "0011"
    assert records.REPO_ROOT == repository
    records.verify_frozen_files()
    assert compiler.CONTRACT_PATH == repository / "docs/contracts/p06/contract.json"
    assert comparisons.FIXTURE_PATH == api_root / "tests/fixtures/effect_comparison/synthetic_effect_comparison_v1.json"
    assert replays.FIXTURE_PATH == api_root / "tests/fixtures/spot_replay/runtime_wc01.json"
    assert comparisons.PROFILE_PATH == repository / "docs/implementation/EFFECT_COMPARISON_PROFILE.md"
    assert replays.PROFILE_PATH == repository / "docs/implementation/SPOT_REPLAY_RUNTIME_PROFILE.md"
    for path in (compiler.CONTRACT_PATH, comparisons.FIXTURE_PATH, replays.FIXTURE_PATH,
                 comparisons.PROFILE_PATH, replays.PROFILE_PATH):
        assert path.is_file()
