"""FastAPI application factory. Every route except /healthz and /readyz requires a verified principal."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, TypeVar

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DataError, OperationalError, SQLAlchemyError
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
        data = p02.strict_loads(b"".join(chunks).decode("utf-8"))
    except (p02.Invalid, ValueError, UnicodeDecodeError, RecursionError) as error:
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

    def run(session: Session, call: Callable[[], Any], retry: str = "SAFE_SAME_KEY") -> Any:
        try:
            return call()
        except SQLAlchemyError as error:
            session.rollback()
            if isinstance(error, OperationalError):
                raise service_unavailable(retry) from None
            if isinstance(error, DataError):  # for example U+0000 in a path segment
                raise invalid("/", "A value cannot be stored as sent.", "invalid_character") from None
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
        # Intake has no idempotency key: after an outage the client must check the saved list before repeating.
        return run(session, lambda: service.create_request(session, principal, body), retry="RECONCILE")

    @private.get("/research/requests")
    def list_requests(principal: Principal = Depends(require_principal),
                      session: Session = Depends(get_session)) -> dict[str, Any]:
        requests, has_more = run(session, lambda: service.list_requests(session, principal))
        return {"requests": requests, "has_more": has_more}

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
