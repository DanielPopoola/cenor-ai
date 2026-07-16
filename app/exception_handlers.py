from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

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


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _render_alert(
    request: Request, message: str, request_id: str, status: int
) -> HTMLResponse:
    from web.templating import templates

    html = templates.get_template("_alert.html").render(
        {"request": request, "message": message, "request_id": request_id}
    )
    return HTMLResponse(content=html, status_code=status)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CernoError)
    async def handle_domain_error(request: Request, exc: CernoError):
        status = _status_for(exc)
        request_id = get_request_id()
        _log.warning(
            "domain_error",
            path=request.url.path,
            error_type=type(exc).__name__,
            message=exc.message,
            cause=str(exc.__cause__) if exc.__cause__ else None,
        )
        if _is_htmx(request):
            return _render_alert(request, exc.message, request_id, status)
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
    ):
        request_id = get_request_id()
        _log.warning(
            "request_validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )
        message = "Request did not match the expected shape."
        if _is_htmx(request):
            return _render_alert(request, message, request_id, 422)
        envelope = APIResponse.fail(
            ErrorDetail(
                code="RequestValidationError",
                message=message,
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=422, content=envelope.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        request_id = get_request_id() or getattr(request.state, "request_id", "")
        _log.error(
            "unhandled_exception",
            path=request.url.path,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        message = "Something went wrong on our end."
        if _is_htmx(request):
            return _render_alert(request, message, request_id, 500)
        envelope = APIResponse.fail(
            ErrorDetail(
                code="InternalServerError",
                message=message,
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=500, content=envelope.model_dump())
