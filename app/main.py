from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.exception_handlers import register_exception_handlers
from common.logger import configure_logging, get_logger
from common.middleware import RequestIDMiddleware
from common.rate_limit import RateLimitMiddleware
from config import Settings, get_settings
from db.session import Database

_log = get_logger("app.main")


class PanicRecoveryMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            _log.error(
                "unhandled_exception_at_middleware_layer",
                path=scope.get("path", "unknown"),
                error_type=type(exc).__name__,
                message=str(exc),
            )

            response = JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "InternalServerError",
                        "message": "Something went wrong on our end.",
                        "request_id": "",
                    },
                },
            )
            await response(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level="DEBUG" if settings.is_development else "INFO")

    database = Database(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _log.info("startup_sequence_begin", env=settings.env)
        _log.info("startup_sequence_complete")
        yield
        _log.info("shutdown_begin")
        database.engine.dispose()
        _log.info("shutdown_complete")

    app = FastAPI(lifespan=lifespan)

    app.state.settings = settings
    app.state.database = database

    from auth.service import OAuthStateStore

    app.state.oauth_state_store = OAuthStateStore()

    from ai.setup import create_ai_service

    app.state.ai_service = create_ai_service(settings)

    register_exception_handlers(app)

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(PanicRecoveryMiddleware)

    from api.v1.router import api_router

    app.include_router(api_router, prefix="/api/v1")

    from web.routes import router as web_router

    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory="web/static"), name="static")

    return app


app = create_app()
