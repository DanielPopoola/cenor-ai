import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import Settings

_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Fixed-window counter per (client_ip, bucket). Bucket is chosen by
    matching the request path against configured prefixes — e.g. any
    /auth/* path shares one tighter bucket, session-creation shares
    another, everything else falls into the default bucket.
    """

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self._settings = settings
        # {(client_ip, bucket): (window_start_epoch, count)}
        self._windows: dict[tuple[str, str], tuple[float, int]] = defaultdict(
            lambda: (0.0, 0)
        )

    def _bucket_for(self, path: str) -> tuple[str, int]:
        if path.startswith("/api/v1/auth"):
            return "auth", self._settings.rate_limit_auth_per_minute
        if path.startswith("/api/v1/sessions") and path.count("/") <= 3:
            # matches POST /api/v1/sessions (creation) but not deeper
            # paths like /api/v1/sessions/{id}/turns
            return "session_create", self._settings.rate_limit_session_create_per_minute
        return "default", self._settings.rate_limit_default_per_minute

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        bucket, limit = self._bucket_for(request.url.path)
        key = (client_ip, bucket)

        now = time.time()
        window_start, count = self._windows[key]
        if now - window_start >= _WINDOW_SECONDS:
            window_start, count = now, 0

        count += 1
        self._windows[key] = (window_start, count)

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "RateLimitExceeded",
                        "message": "Too many requests. Please slow down.",
                        "request_id": "",
                    },
                },
            )

        return await call_next(request)
