"""HTTP error envelope from the P02 contract (`http_error_body`)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@dataclass
class AppError(Exception):
    status: int
    stage: str
    outcome: str
    code: str
    findings: list[dict[str, str]] = field(default_factory=list)
    retry: str = "NOT_RETRYABLE"
    headers: dict[str, str] | None = None

    def body(self) -> dict[str, Any]:
        return {"operation_id": str(uuid.uuid4()), "stage": self.stage, "outcome": self.outcome,
                "code": self.code, "findings": self.findings, "retry": self.retry}


def finding(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def not_found(what: str = "record") -> AppError:
    return AppError(404, "READ", "NOT_FOUND", "not_found",
                    [finding("not_found", "/", f"The requested {what} was not found.")])


def invalid(path: str, detail: str, code: str = "invalid_value") -> AppError:
    return AppError(422, "VALIDATION", "INVALID_INPUT", "validation_error", [finding(code, path, detail)])


def auth_error(status: int, code: str, detail: str, www: bool = True) -> AppError:
    outcome = "UNAVAILABLE" if status == 503 else "UNAUTHORIZED"
    headers = {"WWW-Authenticate": "Bearer"} if www and status == 401 else None
    retry = "SAFE_SAME_KEY" if status == 503 or code == "auth_expired" else "NOT_RETRYABLE"
    return AppError(status, "AUTHENTICATION", outcome, code, [finding(code, "/", detail)], retry, headers)


def service_unavailable() -> AppError:
    return AppError(503, "READ", "UNAVAILABLE", "service_unavailable",
                    [finding("service_unavailable", "/", "A required service is unavailable. Retry later.")],
                    "SAFE_SAME_KEY")


def _pointer(loc: tuple[Any, ...]) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in loc if p != "body"]
    return "/" + "/".join(parts) if parts else "/"


def install_handlers(app: Any) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, error: AppError) -> JSONResponse:
        return JSONResponse(error.body(), status_code=error.status, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, error: RequestValidationError) -> JSONResponse:
        findings = [finding(item["type"], _pointer(tuple(item["loc"])), item["msg"]) for item in error.errors()][:20]
        body = AppError(422, "VALIDATION", "INVALID_INPUT", "validation_error", findings).body()
        return JSONResponse(body, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, error: StarletteHTTPException) -> JSONResponse:
        if error.status_code == 404:
            return JSONResponse(not_found("route").body(), status_code=404)
        body = AppError(error.status_code, "VALIDATION", "INVALID_INPUT", "validation_error",
                        [finding("http_error", "/", "The request cannot be handled.")]).body()
        return JSONResponse(body, status_code=error.status_code, headers=getattr(error, "headers", None))
