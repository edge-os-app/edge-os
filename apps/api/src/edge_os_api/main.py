"""FastAPI application factory. Every route except /healthz and /readyz requires a verified principal."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, TypeVar

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DataError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import Session

from edge_os_api.accounts import views as account_views
from edge_os_api.agent_context import controls as agent_context
from edge_os_api.research import comparison_runs as effect_run
from edge_os_api.research import investigation_adoption as investigation_adoption
from edge_os_api.research import history_dataset, history_payload_binding, investigation_jobs, market_adoption
from edge_os_api.usage import quota, rate_limit
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research import service as service
from edge_os_api.research.attempt_store import AdvisoryLockGuard
from edge_os_api.research.hermes_interpreter import HermesInterpreterConfig, HermesTurnRunner
from edge_os_api.research.interpretation_workflow import LOCAL_FAKE_CONFIG, HermesResearch
from edge_os_api.replay import saved_runs as spot_replay_api
from edge_os_api.core.authentication import Principal, Verifier, require_principal
from edge_os_api.core.database import current_revision, make_engine, make_session_factory, require_head, script_head
from edge_os_api.core.errors import AppError, finding, install_handlers, invalid, not_found, service_unavailable
from edge_os_api.research.fixture_interpreter import samples
from edge_os_api.core.request_schemas import ClarificationBody, EffectAttemptBody, EffectRunBody, IntakeBody, HistoryInvestigationBody, InvestigationBody, InvestigationJobBody, MarketAdoptionBody, NansenReportBody, PublicationBody, RetryBody, SpotReplayBody
from edge_os_api.core.settings import ConfigError, Settings, load_settings
from edge_os_api.core.research import released_runtime_bootstrap
from edge_os_api.core.research.operating_release import ReleaseRefused
from edge_os_api.core.research.released_source_runtime import ReleasedSourceRuntime, release_view
from edge_os_api.wallet_setup import router as wallet_setup
from edge_os_api.wallet_setup.adapter import build_wallet_provider
from edge_os_api.consent import routes as consent_routes
from edge_os_api.core.financial_services import build_financial_services
from edge_os_api.execution import routes as action_routes
from edge_os_api.funding import routes as funding_routes
from edge_os_api.recovery import routes as recovery_routes
from edge_os_api.revocation import routes as removal_routes
from edge_os_api.stops import routes as stop_routes

log = logging.getLogger("edge_os")
MAX_BODY_BYTES = 256 * 1024
ModelT = TypeVar("ModelT", bound=BaseModel)


MAX_JSON_DEPTH = 100  # strategies allow expression depth 64; envelope and wrappers add a few levels


def _scan(node: Any) -> tuple[bool, int]:
    """Iterative walk: (contains U+0000, maximum nesting depth). PostgreSQL text and jsonb cannot hold U+0000."""
    has_nul, deepest, stack = False, 0, [(node, 1)]
    while stack:
        item, depth = stack.pop()
        deepest = max(deepest, depth)
        if depth > MAX_JSON_DEPTH:
            return has_nul, deepest
        if isinstance(item, str):
            has_nul = has_nul or "\x00" in item
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, dict):
            for key, value in item.items():
                has_nul = has_nul or "\x00" in key
                stack.append((value, depth + 1))
    return has_nul, deepest


async def read_json(request: Request) -> Any:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise invalid("/", "The request body is too large.", "body_too_large")
    chunks, size = [], 0
    async for chunk in request.stream():  # stop reading at the cap, even without a Content-Length
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise invalid("/", "The request body is too large.", "body_too_large")
        chunks.append(chunk)
    try:
        data = record_contract.strict_loads(b"".join(chunks).decode("utf-8"))
    except (record_contract.Invalid, ValueError, UnicodeDecodeError, RecursionError) as error:
        detail = "The body nests too deeply." if isinstance(error, RecursionError) else f"The body is not strict JSON: {error}"
        raise invalid("/", detail, "invalid_json") from None
    has_nul, depth = _scan(data)
    if depth > MAX_JSON_DEPTH:
        raise invalid("/", "The body nests too deeply.", "invalid_json")
    if has_nul:
        raise invalid("/", "Text cannot contain the NUL character (U+0000).", "invalid_character")
    return data


def parse_body(model: type[ModelT], data: Any) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        findings = [finding(item["type"], "/" + "/".join(str(p) for p in item["loc"]), item["msg"])
                    for item in error.errors()][:20]
        raise AppError(422, "VALIDATION", "INVALID_INPUT", "validation_error", findings) from None


def create_app(settings: Settings | None = None, hermes_runner: HermesTurnRunner | None = None,
               research_runtime: ReleasedSourceRuntime | None = None,
               hermes_config: HermesInterpreterConfig | None = None) -> FastAPI:
    """Compose the application. `hermes_runner` is the process boundary of the local Hermes interpreter.

    Only the `hermes_local` setting uses it, and that setting needs it. `hermes_config` is the interpreter configuration
    of the release that runner serves (`research/hermes_relay_composition.py`); without one the runner serves the local
    fake provider configuration. A configuration needs its runner and is refused in production.

    `research_runtime` is a composed operating release (`core/research/released_source_runtime.py`). Without one, the
    server bootstrap composes the approved code-owned release, the same one the worker composes; none exists and no
    setting adds one, so the default reaches no provider.
    """
    settings = settings or load_settings()
    if settings.interpreter == "hermes_local" and hermes_runner is None:
        raise ConfigError("invalid configuration: interpreter: hermes_local needs a Hermes runner")
    if hermes_config is not None and (settings.interpreter != "hermes_local" or hermes_runner is None
                                      or settings.env == "production"):
        raise ConfigError("invalid configuration: interpreter: a Hermes release configuration needs hermes_local, "
                          "its Hermes runner and a non-production environment")
    if research_runtime is None:
        try:
            research_runtime = released_runtime_bootstrap.server_research_runtime(settings)
        except ReleaseRefused as error:
            raise ConfigError(f"invalid configuration: research_runtime: {error.code}") from None
    if research_runtime is not None:
        if research_runtime.release.kind == "STAND_IN" and settings.env == "production":
            raise ConfigError("invalid configuration: research_runtime: a stand-in release is refused in production")
        if research_runtime.release.nansen is not None and settings.nansen_research_mode != "unavailable":
            raise ConfigError("invalid configuration: research_runtime: a release Nansen part and "
                              "nansen_research_mode cannot both serve Nansen reports")
        try:
            history_dataset.check_release_source(research_runtime)
        except ReleaseRefused as error:
            raise ConfigError(f"invalid configuration: research_runtime: {error.code}") from None
    engine = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    try:
        require_head(engine)
    except SQLAlchemyError:
        engine.dispose()
        raise
    verifier = Verifier(settings.privy_app_id, settings.verification_keys)
    # The local fixture is the only available wallet provider; production uses the fail-closed one.
    wallet_provider = build_wallet_provider(settings.wallet_provider)
    session_factory = make_session_factory(engine)
    started_at = service.utcnow().isoformat()
    hermes = (HermesResearch(hermes_runner, session_factory, AdvisoryLockGuard(engine), time.monotonic,
                             hermes_config or LOCAL_FAKE_CONFIG)
              if settings.interpreter == "hermes_local" and hermes_runner is not None else None)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if hermes is not None:
            try:  # closes only attempts that nobody runs, publishes saved accepted results, and makes no model call
                hermes.recover_all()
            except Exception as error:  # noqa: BLE001 - a failed recovery must not stop the service from starting
                log.error("interpretation recovery failed: %s", type(error).__name__)
        yield
        engine.dispose()

    docs = settings.docs_enabled
    app = FastAPI(title="Edge OS API", lifespan=lifespan, docs_url="/docs" if docs else None,
                  redoc_url="/redoc" if docs else None, openapi_url="/openapi.json" if docs else None)
    app.state.settings, app.state.verifier = settings, verifier
    app.state.engine, app.state.session_factory, app.state.hermes = engine, session_factory, hermes
    app.state.wallet_provider = wallet_provider
    app.state.research_runtime = research_runtime
    # One composition of the accepted financial services. Its provider ports follow `execution_mode`:
    # authored fixtures in local/test configuration, fail-closed unavailable ports in production.
    app.state.financial = build_financial_services(session_factory, settings)
    install_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"], allow_credentials=False)

    def get_session(request: Request) -> Any:
        with request.app.state.session_factory() as session:
            yield session

    public = APIRouter()

    @public.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "build_sha": settings.resolved_build_sha, "started_at": started_at}

    @public.get("/readyz")
    def readyz() -> JSONResponse:
        try:
            revision, head = current_revision(engine), script_head()
            with engine.connect() as connection:
                connection.execute(text("select 1"))
            with session_factory() as session:
                mismatches = quota.cap_mismatches(session, investigation_jobs.caps(settings))
        except SQLAlchemyError:
            return JSONResponse({"status": "unavailable", "reason": "database_unavailable"}, status_code=503)
        # Reason codes only; no value from configuration or the database is echoed.
        if revision != head:
            return JSONResponse({"status": "unavailable", "reason": "schema_drift"}, status_code=503)
        if not verifier.keys:
            return JSONResponse({"status": "unavailable", "reason": "verification_keys_missing"}, status_code=503)
        shared = [item for item in mismatches if item["scope"] == "GLOBAL"]
        if shared:  # the shared cap affects every owner
            return JSONResponse({"status": "unavailable", "reason": "quota_cap_mismatch",
                                 "resources": sorted(item["resource"] for item in shared)}, status_code=503)
        ready: dict[str, Any] = {"status": "ready", "schema_revision": revision}
        owners = {item["resource"]: item["allocations"] for item in mismatches if item["scope"] == "OWNER"}
        if owners:  # only those owners' new research starts pause; counts only, no owner id or value
            ready["attention"] = {"owner_quota_cap_mismatch": owners}
        return JSONResponse(ready)

    def limit_writes(request: Request, principal: Principal = Depends(require_principal)) -> None:
        """Count every authenticated write in the owner's shared PostgreSQL window; reads are not limited."""
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return
        with session_factory() as session:
            try:
                rate_limit.count_write(session, principal.user_id, settings.write_rate_per_minute)
            except SQLAlchemyError:
                session.rollback()
                raise service_unavailable("SAFE_SAME_KEY") from None

    private = APIRouter(prefix="/v1", dependencies=[Depends(require_principal), Depends(limit_writes)])

    def run(session: Session, call: Callable[[], Any], retry: str = "SAFE_SAME_KEY") -> Any:
        try:
            return call()
        except SQLAlchemyError as error:
            session.rollback()
            if isinstance(error, (OperationalError, PoolTimeout)):  # refused connection or no free connection: the service is unavailable
                raise service_unavailable(retry) from None
            if isinstance(error, DataError):  # for example U+0000 in a path segment
                raise invalid("/", "A value cannot be stored as sent.", "invalid_character") from None
            raise

    @private.get("/me")
    def me(principal: Principal = Depends(require_principal)) -> dict[str, str]:
        return {"user_id": str(principal.user_id)}

    @private.get("/financial/provider")
    def financial_provider() -> dict[str, Any]:
        return app.state.financial.ports.describe()

    @private.get("/interpreter")
    def interpreter_info() -> dict[str, Any]:
        return {"interpreter": hermes.label() if hermes else service.INTERPRETER.label(), "samples": samples()}

    @private.post("/spot-replays")
    def create_spot_replay(data: Any = Depends(read_json), principal: Principal = Depends(require_principal),
                           session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(SpotReplayBody, data)
        status, result = run(session, lambda: spot_replay_api.create_spot_replay(session, principal, body),
                             retry="RECONCILE")
        headers = {"Idempotent-Replay": "true"} if status == 200 else {}
        return JSONResponse(result, status_code=status, headers=headers)

    @private.get("/spot-replays/{replay_id}")
    def get_spot_replay(replay_id: str, principal: Principal = Depends(require_principal),
                        session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: spot_replay_api.get_spot_replay(session, principal, replay_id))

    @private.post("/research/requests", status_code=201)
    def create_request(data: Any = Depends(read_json), principal: Principal = Depends(require_principal),
                       session: Session = Depends(get_session)) -> Any:
        body = parse_body(IntakeBody, data).model_dump()
        # Intake has no idempotency key: after an outage the client must check the saved list before repeating.
        create = hermes.create_request if hermes else service.create_request
        return run(session, lambda: create(session, principal, body), retry="RECONCILE")

    @private.get("/research/requests")
    def list_requests(principal: Principal = Depends(require_principal),
                      session: Session = Depends(get_session)) -> dict[str, Any]:
        list_saved = hermes.list_requests if hermes else service.list_requests
        requests, has_more = run(session, lambda: list_saved(session, principal))
        return {"requests": requests, "has_more": has_more}

    @private.get("/research/requests/{intake_id}")
    def get_request(intake_id: str, principal: Principal = Depends(require_principal),
                    session: Session = Depends(get_session)) -> Any:
        parsed = service.parse_uuid(intake_id)
        if parsed is None:
            raise not_found()
        return run(session, lambda: service.load_bundle(session, principal, parsed, hermes))

    @private.get("/research/requests/{intake_id}/investigation-proposal")
    def investigation_proposal(intake_id: str, principal: Principal = Depends(require_principal),
                              session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_adoption.get_proposal(session, principal, intake_id))

    @private.post("/research/requests/{intake_id}/investigations")
    def save_investigation(intake_id: str, data: Any = Depends(read_json),
                           principal: Principal = Depends(require_principal),
                           session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(InvestigationBody, data)
        status, result = run(session, lambda: investigation_adoption.create_declaration(
            session, principal, intake_id, body), retry="RECONCILE")
        return JSONResponse(result, status_code=status)

    @private.get("/research/history-sources")
    def history_sources() -> dict[str, Any]:
        """The declared recorded sources. All are SYNTHETIC recordings; none is observed market history."""
        return {**history_dataset.catalog(settings.research_source_clients == "authored_http", research_runtime),
                "mode": settings.research_history_mode, "source_clients": settings.research_source_clients,
                "operating_release": None if research_runtime is None else release_view(research_runtime)}

    @private.post("/research/requests/{intake_id}/history-investigations")
    def save_history_investigation(intake_id: str, data: Any = Depends(read_json),
                                   principal: Principal = Depends(require_principal),
                                   session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(HistoryInvestigationBody, data)
        status, result = run(session, lambda: investigation_adoption.create_history_declaration(
            session, principal, intake_id, body, research_runtime), retry="RECONCILE")
        return JSONResponse(result, status_code=status)

    @private.get("/research/requests/{intake_id}/history-investigations")
    def list_history_investigations(intake_id: str, principal: Principal = Depends(require_principal),
                                    session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_adoption.list_history_declarations(session, principal, intake_id))

    @private.get("/research/requests/{intake_id}/history-investigations/{declaration_id}")
    def get_history_investigation(intake_id: str, declaration_id: str,
                                  principal: Principal = Depends(require_principal),
                                  session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_adoption.get_history_declaration(
            session, principal, intake_id, declaration_id))

    @private.post("/research/requests/{intake_id}/history-investigations/{declaration_id}/jobs")
    def start_investigation_job(intake_id: str, declaration_id: str, data: Any = Depends(read_json),
                                principal: Principal = Depends(require_principal),
                                session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(InvestigationJobBody, data)
        status, result = run(session, lambda: investigation_jobs.start_job(
            session, principal, settings, intake_id, declaration_id, body, research_runtime), retry="RECONCILE")
        return JSONResponse(result, status_code=status)

    @private.get("/research/requests/{intake_id}/history-investigations/{declaration_id}/jobs")
    def list_investigation_jobs(intake_id: str, declaration_id: str,
                                principal: Principal = Depends(require_principal),
                                session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_jobs.list_jobs(session, principal, intake_id, declaration_id))

    @private.get("/research/investigation-jobs/{job_id}")
    def get_investigation_job(job_id: str, principal: Principal = Depends(require_principal),
                              session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_jobs.get_job(session, principal, job_id))

    @private.post("/research/investigation-jobs/{job_id}/cancel")
    def cancel_investigation_job(job_id: str, principal: Principal = Depends(require_principal),
                                 session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_jobs.cancel_job(session, principal, settings, job_id),
                   retry="RECONCILE")

    @private.get("/research/investigation-reports/{report_id}")
    def get_investigation_report(report_id: str, principal: Principal = Depends(require_principal),
                                 session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_jobs.get_report(session, principal, report_id))

    @private.post("/research/requests/{intake_id}/nansen-reports")
    def start_nansen_report(intake_id: str, data: Any = Depends(read_json),
                            principal: Principal = Depends(require_principal),
                            session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(NansenReportBody, data)
        status, result = run(session, lambda: investigation_jobs.start_nansen_job(
            session, principal, settings, intake_id, body, research_runtime), retry="RECONCILE")
        return JSONResponse(result, status_code=status)

    @private.get("/research/requests/{intake_id}/nansen-reports")
    def list_nansen_reports(intake_id: str, principal: Principal = Depends(require_principal),
                            session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_jobs.list_nansen_jobs(session, principal, settings,
                                                                                 intake_id, research_runtime))

    @private.get("/research/nansen-reports/{report_id}")
    def get_nansen_report(report_id: str, principal: Principal = Depends(require_principal),
                          session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_jobs.get_nansen_report(session, principal, report_id))

    @private.get("/research/history-datasets")
    def list_history_datasets(principal: Principal = Depends(require_principal),
                              session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: history_dataset.list_datasets(session, principal))

    @private.get("/research/history-datasets/{dataset_id}")
    def get_history_dataset(dataset_id: str, principal: Principal = Depends(require_principal),
                            session: Session = Depends(get_session)) -> Any:
        def view() -> dict[str, Any]:
            row = history_dataset.owned_dataset(session, principal, dataset_id)
            return {**history_dataset.dataset_view(row),
                    "payload_binding": history_payload_binding.binding_state(session, row, principal.user_id)}
        return run(session, view)

    @private.post("/research/requests/{intake_id}/market-adoptions")
    def adopt_market(intake_id: str, data: Any = Depends(read_json), principal: Principal = Depends(require_principal),
                     session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(MarketAdoptionBody, data)
        status, result = run(session, lambda: market_adoption.adopt_dataset_market(session, principal, intake_id, body),
                             retry="RECONCILE")
        return JSONResponse(result, status_code=status)

    @private.get("/research/budget")
    def research_budget(principal: Principal = Depends(require_principal),
                        session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_jobs.get_budget(session, principal, settings))

    @private.get("/research/requests/{intake_id}/investigations")
    def get_investigations(intake_id: str, principal: Principal = Depends(require_principal),
                           session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_adoption.list_declarations(session, principal, intake_id))

    @private.get("/research/requests/{intake_id}/investigations/{declaration_id}")
    def get_investigation(intake_id: str, declaration_id: str,
                          principal: Principal = Depends(require_principal),
                          session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: investigation_adoption.get_declaration(
            session, principal, intake_id, declaration_id))

    @private.post("/research/requests/{intake_id}/investigations/{declaration_id}/effect-runs")
    def adopt_effect_run(intake_id: str, declaration_id: str, data: Any = Depends(read_json),
                         principal: Principal = Depends(require_principal),
                         session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(EffectRunBody, data)
        status, result = run(session, lambda: effect_run.adopt_effect_run(
            session, principal, intake_id, declaration_id, body), retry="RECONCILE")
        return JSONResponse(result, status_code=status)

    @private.get("/research/requests/{intake_id}/effect-runs")
    def list_effect_runs(intake_id: str, principal: Principal = Depends(require_principal),
                         session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: effect_run.list_effect_runs(session, principal, intake_id))

    @private.post("/research/requests/{intake_id}/effect-runs/{run_id}/attempts")
    def execute_effect_run(intake_id: str, run_id: str, data: Any = Depends(read_json),
                           principal: Principal = Depends(require_principal),
                           session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(EffectAttemptBody, data)
        status, result = run(session, lambda: effect_run.execute_effect_run(
            session, principal, intake_id, run_id, body), retry="RECONCILE")
        return JSONResponse(result, status_code=status)

    @private.get("/research/requests/{intake_id}/effect-runs/{run_id}")
    def get_effect_run(intake_id: str, run_id: str, principal: Principal = Depends(require_principal),
                       session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: effect_run.get_effect_run(session, principal, intake_id, run_id))

    @private.post("/research/requests/{intake_id}/clarifications")
    def answer(intake_id: str, data: Any = Depends(read_json), principal: Principal = Depends(require_principal),
               session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(ClarificationBody, data).model_dump()
        if hermes is not None:
            status, bundle = run(session, lambda: hermes.answer_question(session, principal, intake_id, body))
            return JSONResponse(bundle, status_code=status)
        if body["answer_text"] is not None:
            raise invalid("/answer_text", "The fixture interpreter reads listed choices only.", "free_text_not_supported")
        return JSONResponse(run(session, lambda: service.answer_question(session, principal, intake_id, body)),
                            status_code=201)

    @private.post("/research/requests/{intake_id}/interpretation-retries")
    def retry_interpretation(intake_id: str, data: Any = Depends(read_json),
                             principal: Principal = Depends(require_principal),
                             session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(RetryBody, data).model_dump()
        if hermes is None:
            raise AppError(409, "VALIDATION", "CONFLICTED", "parent_revision_conflict", [finding(
                "retry_unavailable", "/", "The fixture interpreter makes no attempts, so there is nothing to retry.")])
        status, bundle = run(session, lambda: hermes.retry(session, principal, intake_id, body), retry="RECONCILE")
        return JSONResponse(bundle, status_code=status)

    @private.post("/strategies/{strategy_id}/revisions")
    def publish(strategy_id: str, data: Any = Depends(read_json), principal: Principal = Depends(require_principal),
                session: Session = Depends(get_session)) -> JSONResponse:
        body = parse_body(PublicationBody, data).model_dump()
        if service.parse_uuid(body["operation_id"]) is None:
            raise invalid("/operation_id", "The operation ID must be a UUID.", "invalid_uuid")
        status, result = run(session, lambda: service.publish(session, principal, strategy_id, body))
        return JSONResponse(result, status_code=status, headers={"Idempotent-Replay": "true"} if status == 200 else None)

    @private.get("/strategies/{strategy_id}/revisions/{revision_id}")
    def revision(strategy_id: str, revision_id: str, principal: Principal = Depends(require_principal),
                 session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: service.get_revision(session, principal, strategy_id, revision_id))

    @private.get("/operations/{operation_id}")
    def operation(operation_id: str, principal: Principal = Depends(require_principal),
                  session: Session = Depends(get_session)) -> Any:
        return run(session, lambda: service.get_operation(session, principal, operation_id))

    app.include_router(public)
    app.include_router(private)
    write_limited = [Depends(limit_writes)]
    app.include_router(account_views.router, dependencies=write_limited)
    app.include_router(agent_context.router, dependencies=write_limited)
    app.include_router(wallet_setup.router, dependencies=write_limited)
    for financial_router in (funding_routes.router, consent_routes.router, action_routes.router,
                             recovery_routes.router, stop_routes.router, removal_routes.router):
        app.include_router(financial_router, dependencies=write_limited)
    return app
