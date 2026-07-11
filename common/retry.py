import asyncio
import functools
import time
from typing import Any, Callable, TypeVar, overload, Awaitable, cast
from typing_extensions import ParamSpec

from common.logger import get_logger
from config import get_settings

T = TypeVar("T")
P = ParamSpec("P")

_log = get_logger("common.retry")
settings = get_settings()


@overload
def retry_transient(
    max_attempts: int = ...,
    exceptions: tuple[type[Exception], ...] = ...,
    backoff_seconds: float = ...,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]: ...


@overload
def retry_transient(
    max_attempts: int = ...,
    exceptions: tuple[type[Exception], ...] = ...,
    backoff_seconds: float = ...,
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def retry_transient(
    max_attempts: int = settings.max_retry_attempts,
    exceptions: tuple[type[Exception], ...] = (),
    backoff_seconds: float = 0.5,
):
    def decorator(func: Callable[P, T] | Callable[P, Awaitable[T]]) -> Any:
        if asyncio.iscoroutinefunction(func):
            # Narrow the type for the async branch
            async_func = cast(Callable[P, Awaitable[T]], func)

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                last_exc: Exception | None = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return await async_func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        _log.warning(
                            "transient_failure_retrying",
                            attempt=attempt,
                            error=str(exc),
                        )
                        if attempt < max_attempts:
                            await asyncio.sleep(backoff_seconds * attempt)
                raise last_exc  # type: ignore

            return async_wrapper

        # Narrow the type for the sync branch
        sync_func = cast(Callable[P, T], func)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return sync_func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    _log.warning(
                        "transient_failure_retrying", attempt=attempt, error=str(exc)
                    )
                    if attempt < max_attempts:
                        time.sleep(backoff_seconds * attempt)
            raise last_exc  # type: ignore

        return sync_wrapper

    return decorator
