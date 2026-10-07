"""FastAPI application factory. Every route except /healthz and /readyz requires a verified principal."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, TypeVar

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from . import p02, service
from .auth import Principal, Verifier, require_principal
from .db import current_revision, make_engine, make_session_factory, require_head, script_head
from .errors import AppError, finding, install_handlers, invalid, not_found, service_unavailable
from .interpreter import samples
from .schemas import ClarificationBody, IntakeBody, PublicationBody
from .settings import Settings, load_settings

log = logging.getLogger("edge_os")
MAX_BODY_BYTES = 256 * 1024
ModelT = TypeVar("ModelT", bound=BaseModel)


async def read_json(request: Request) -> Any:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise invalid("/", "The request body is too large.", "body_too_large")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise invalid("/", "The request body is too large.", "body_too_large")
    try:
        return p02.strict_loads(raw.decode("utf-8"))
    except (p02.Invalid, ValueError, UnicodeDecodeError) as error:
        raise invalid("/", f"The body is not strict JSON: {error}", "invalid_json") from None


def parse_body(model: type[ModelT], data: Any) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        findings = [finding(item["type"], "/" + "/".join(str(p) for p in item["loc"]), item["msg"])
                    for item in error.errors()][:20]
        raise AppError(422, "VALIDATION", "INVALID_INPUT", "validation_error", findings) from None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    try:
        require_head(engine)
    except SQLAlchemyError:
        engine.dispose()
        raise
    verifier = Verifier(settings.privy_app_id, settings.verification_keys)
    session_factory = make_session_factory(engine)
    started_at = service.utcnow().isoformat()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    docs = settings.docs_enabled
    app = FastAPI(title="Edge OS API", lifespan=lifespan, docs_url="/docs" if docs else None,
                  redoc_url="/redoc" if docs else None, openapi_url="/openapi.json" if docs else None)
    app.state.settings, app.state.verifier = settings, verifier
    app.state.engine, app.state.session_factory = engine, session_factory
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
        except SQLAlchemyError:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        if revision != head or not verifier.keys:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ready", "schema_revision": revision})

    private = APIRouter(prefix="/v1", dependencies=[Depends(require_principal)])

    def run(session: Session, call: Callable[[], Any]) -> Any:
        try:
            return call()
        except SQLAlchemyError as error:
            session.rollback()
            if isinstance(error, OperationalError):
                raise service_unavailable() from None
            raise

    @private.get("/me")
    def me(principal: Principal = Depends(require_principal)) -> dict[str, str]:
        return {"user_id": str(principal.user_id)}

    @private.get("/interpreter")
    def interpreter_info() -> dict[str, Any]:
        return {"interpreter": service.INTERPRETER.label(), "samples": samples()}

    @private.post("/research/requests", status_code=201)
    def create_request(data: Any = Depends(read_json), principal: Principal = Depends(require_principal),
                       session: Session = Depends(get_session)) -> Any:
        body = parse_body(IntakeBody, data).model_dump()
        return run(session, lambda: service.create_request(session, principal, body))

    @private.get("/research/requests")
    def list_requests(principal: Principal = Depends(require_principal),
                      session: Session = Depends(get_session)) -> dict[str, Any]:
        return {"requests": run(session, lambda: service.list_requests(session, principal))}

    @private.get("/research/requests/{intake_id}")
    def get_request(intake_id: str, principal: Principal = Depends(require_principal),
                    session: Session = Depends(get_session)) -> Any:
        parsed = service.parse_uuid(intake_id)
        if parsed is None:
            raise not_found()
        return run(session, lambda: service.load_bundle(session, principal, parsed))

    @private.post("/research/requests/{intake_id}/clarifications", status_code=201)
    def answer(intake_id: str, data: Any = Depends(read_json), principal: Principal = Depends(require_principal),
               session: Session = Depends(get_session)) -> Any:
        body = parse_body(ClarificationBody, data).model_dump()
        return run(session, lambda: service.answer_question(session, principal, intake_id, body))

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
    return app
