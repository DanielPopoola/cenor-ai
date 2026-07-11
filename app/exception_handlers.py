from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common.errors import (
    CernoError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from common.logger import get_logger
from common.middleware import get_request_id
from common.schemas import APIResponse, ErrorDetail

_log = get_logger("exception_handlers")

# Order matters: checked top-to-bottom via isinstance, so a subclass of
# NotFoundError matches here before falling through to the default.
_STATUS_BY_FAMILY: list[tuple[type[CernoError], int]] = [
    (NotFoundError, 404),
    (ValidationError, 422),
    (ConflictError, 409),
    (UnauthorizedError, 401),
]
_DEFAULT_STATUS = 500


def _status_for(exc: CernoError) -> int:
    for family, status in _STATUS_BY_FAMILY:
        if isinstance(exc, family):
            return status
    return _DEFAULT_STATUS


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CernoError)
    async def handle_domain_error(request: Request, exc: CernoError) -> JSONResponse:
        status = _status_for(exc)
        request_id = get_request_id()
        _log.warning(
            "domain_error",
            path=request.url.path,
            error_type=type(exc).__name__,
            message=exc.message,
            cause=str(exc.__cause__) if exc.__cause__ else None,
        )
        envelope = APIResponse.fail(
            ErrorDetail(
                code=type(exc).__name__,
                message=exc.message,
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=status, content=envelope.model_dump())

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = get_request_id()
        _log.warning(
            "request_validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )
        envelope = APIResponse.fail(
            ErrorDetail(
                code="RequestValidationError",
                message="Request did not match the expected shape.",
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=422, content=envelope.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # get_request_id() reads a contextvar that RequestIDMiddleware's
        # `finally` block may already have reset by the time an
        # exception this generic reaches us (it can propagate past the
        # middleware's own cleanup, unlike a registered CernoError which
        # FastAPI's routing layer catches before that cleanup runs).
        # request.state.request_id was set directly on the request
        # object, which isn't torn down the same way — use it as the
        # reliable fallback.
        request_id = get_request_id() or getattr(request.state, "request_id", "")
        _log.error(
            "unhandled_exception",
            path=request.url.path,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        envelope = APIResponse.fail(
            ErrorDetail(
                code="InternalServerError",
                message="Something went wrong on our end.",
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=500, content=envelope.model_dump())
