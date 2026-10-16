"""The loopback launcher of the Hermes relay application, and the interpreter label the application shows.

Pure tests (no database, Docker or network). The launcher refuses with exit 2 before any effect when no release is
approved, the port is invalid, the environment is production or another interpreter, or the handoff is not the bound
release's. With an opened application it serves `create_app` with that application's exact runner and configuration on
127.0.0.1, and closes the application exactly once whatever happens; it never stops the operator's relay.

The label keeps its `{kind, id, notice}` shape. The local fake provider keeps its notice. A LIVE configuration names
its release, provider and model and never claims a call. A SYNTHETIC test release stays visibly SYNTHETIC.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research import hermes_relay_composition as composition
from edge_os_api.research.hermes_relay_composition import bind_release
from edge_os_api.research.interpretation_workflow import LABEL, LOCAL_FAKE_CONFIG, HermesResearch
from test_hermes_relay_composition import (  # noqa: F401 - the fixtures are used by name
    approve, definition, handoff, unreachable, write_handoff,
)

LAUNCHER = Path(__file__).resolve().parents[3] / "scripts" / "hermes_app_mount" / "serve_relay_application.py"


@pytest.fixture
def launcher(monkeypatch: pytest.MonkeyPatch, unreachable) -> Any:  # noqa: F811
    """The launcher module, reading `unreachable` settings; serving or a second factory call fails the test."""
    spec = importlib.util.spec_from_file_location("serve_relay_application", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "load_settings", lambda: unreachable)

    def no_serving(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the launcher served after a refusal")

    monkeypatch.setattr(module.uvicorn, "run", no_serving)
    monkeypatch.setattr(module, "create_app", no_serving)
    return module


def argv(tmp_path: Path, *, port: str = "8765", located: tuple[Path, str] | None = None) -> list[str]:
    path, sha = located or (tmp_path / "operator" / "handoff.json", "0" * 64)
    return ["--handoff-path", str(path), "--handoff-sha256", sha, "--run-id", "launch-unit", "--port", port]


# --- refusals before any effect --------------------------------------------------------------------------------------


def test_with_empty_registries_launch_is_refused_before_the_handoff_engine_or_server(
        launcher, approve, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    approve()  # explicitly empty registries, whatever the ordinary ones hold
    assert composition.RELEASE_DEFINITIONS == () and composition.relay_admission.APPROVED_ACTUAL_RELEASES == frozenset()
    assert launcher.main(argv(tmp_path)) == 2  # `unreachable` fails the test if an engine is opened
    assert "no approved Hermes relay application release" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []  # the named handoff was never created or opened


@pytest.mark.parametrize("port", ["0", "65536", "-1", "http", "80.5"])
def test_an_invalid_port_is_refused_before_settings_are_read(launcher, monkeypatch: pytest.MonkeyPatch,
                                                             tmp_path: Path, port: str) -> None:
    monkeypatch.setattr(launcher, "load_settings", lambda: pytest.fail("settings were read"))
    with pytest.raises(SystemExit) as refused:
        launcher.main(argv(tmp_path, port=port))
    assert refused.value.code == 2 and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("update", [{"env": "production"}, {"interpreter": "fixture"}])
def test_production_or_another_interpreter_is_refused(
        launcher, monkeypatch: pytest.MonkeyPatch, approve, unreachable, tmp_path: Path,  # noqa: F811
        capsys: pytest.CaptureFixture[str], update: dict[str, str]) -> None:
    approve(definition())
    monkeypatch.setattr(launcher, "load_settings", lambda: unreachable.model_copy(update=update))
    assert launcher.main(argv(tmp_path)) == 2
    assert capsys.readouterr().err.startswith("refused: ") and list(tmp_path.iterdir()) == []


def test_a_handoff_that_is_not_the_bound_releases_is_refused_before_any_engine(launcher, approve,  # noqa: F811
                                                                                tmp_path: Path) -> None:
    [given] = approve(definition())
    located = write_handoff(tmp_path / "operator", handoff(tmp_path, given, shutdown_owner="application"))
    assert launcher.main(argv(tmp_path, located=located)) == 2
    assert launcher.main(argv(tmp_path, located=(located[0], "0" * 64))) == 2
    assert sorted(path.name for path in tmp_path.iterdir()) == ["operator"]


# --- serving one opened application ----------------------------------------------------------------------------------


class Opened:
    """Stands in for `HermesApplication`: the runner/config pair, the release and a counted close. No relay control."""

    def __init__(self) -> None:
        self.runner, self.config, self.closed, self.startup_recovery = object(), object(), 0, [{"attempt_id": "a"}]
        self.release = type("Release", (), {"actual": type("Actual", (), {"release": type(
            "Relay", (), {"release_id": "SYNTHETIC-launch-1"})})})

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def serving(launcher, monkeypatch: pytest.MonkeyPatch, unreachable) -> dict[str, Any]:  # noqa: F811
    seen: dict[str, Any] = {"opened": Opened()}

    def open_application(settings: Any, **kwargs: Any) -> Opened:
        seen["open"] = (settings, kwargs)
        return seen["opened"]

    def factory(settings: Any, **kwargs: Any) -> object:
        seen["factory"] = (settings, kwargs)
        seen["app"] = object()
        return seen["app"]

    def run(app: object, **kwargs: Any) -> None:
        seen["run"] = (app, kwargs, seen["opened"].closed)

    monkeypatch.setattr(launcher, "open_hermes_application", open_application)
    monkeypatch.setattr(launcher, "create_app", factory)
    monkeypatch.setattr(launcher.uvicorn, "run", run)
    seen["module"] = launcher
    return seen


def test_an_opened_application_is_served_on_loopback_with_its_exact_runner_and_config_then_closed_once(
        serving: dict[str, Any], unreachable, tmp_path: Path,  # noqa: F811
        capsys: pytest.CaptureFixture[str]) -> None:
    located = (tmp_path / "operator" / "handoff.json", "1" * 64)
    assert serving["module"].main(argv(tmp_path, port="8765", located=located)) == 0

    opened = serving["opened"]
    assert serving["open"] == (unreachable, {"handoff_path": located[0], "handoff_sha256": "1" * 64,
                                             "run_id": "launch-unit"})
    assert serving["factory"] == (unreachable, {"hermes_runner": opened.runner, "hermes_config": opened.config})
    app, options, closed_while_serving = serving["run"]
    assert app is serving["app"] and options == {"host": "127.0.0.1", "port": 8765, "log_level": "warning"}
    assert closed_while_serving == 0 and opened.closed == 1
    assert '"serving": "SYNTHETIC-launch-1"' in capsys.readouterr().out


@pytest.mark.parametrize("failing", ["create_app", "run"])
def test_a_factory_or_server_failure_closes_the_opened_application_exactly_once(
        serving: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failing: str) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(serving["module"].uvicorn if failing == "run" else serving["module"], failing, boom)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        serving["module"].main(argv(tmp_path))
    assert serving["opened"].closed == 1


def test_the_application_close_disposes_only_its_own_engine(approve, tmp_path: Path) -> None:  # noqa: F811
    from test_hermes_relay_composition import endpoint, lazy_engine

    [given] = approve(definition())
    relay = tmp_path / "relay"
    for folder in ("grants", "revocations", "state"):
        (relay / folder).mkdir(parents=True)
    app = composition.compose_application(bind_release(given), lazy_engine(), endpoint=endpoint(relay),
                                          run_id="launch-unit", evidence_dir=tmp_path / "jobs")
    disposed: list[bool] = []
    app.engine.dispose = lambda: disposed.append(True)  # type: ignore[method-assign]
    before = sorted(str(path) for path in tmp_path.rglob("*"))
    app.close()
    assert disposed == [True] and sorted(str(path) for path in tmp_path.rglob("*")) == before


# --- the interpreter label --------------------------------------------------------------------------------------


def research(config: Any) -> HermesResearch:
    return HermesResearch(object(), lambda: None, object(), lambda: 0.0, config)  # type: ignore[arg-type]


def test_the_local_fake_provider_keeps_its_label() -> None:
    assert research(LOCAL_FAKE_CONFIG).label() == LABEL and research(LOCAL_FAKE_CONFIG).label() is not LABEL
    assert set(LABEL) == {"kind", "id", "notice"} and "No real model" in LABEL["notice"]


def test_a_live_release_label_names_the_configured_release_and_claims_no_call(approve) -> None:  # noqa: F811
    [given] = approve(definition(record_fields={"release_id": "SYNTHETIC-app-1"}))
    label = research(bind_release(given).config).label()

    assert set(label) == {"kind", "id", "notice"}
    assert (label["kind"], label["id"]) == ("HERMES_LIVE_RELEASE", "SYNTHETIC-app-1")
    for named in ("SYNTHETIC-app-1", "synthetic-provider", "synthetic-model/1", "USD 0.30"):
        assert named in label["notice"]
    assert "does not show that a model call completed" in label["notice"] and "No real model" not in label["notice"]
