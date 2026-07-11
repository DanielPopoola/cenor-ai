import pytest

from common.retry import retry_transient


class _TransientError(Exception):
    pass


class _NonTransientError(Exception):
    pass


def test_sync_retries_and_succeeds_after_transient_failure():
    calls = {"n": 0}

    @retry_transient(max_attempts=3, exceptions=(_TransientError,), backoff_seconds=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _TransientError()
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 2


def test_sync_exhausts_attempts_and_reraises():
    calls = {"n": 0}

    @retry_transient(max_attempts=2, exceptions=(_TransientError,), backoff_seconds=0)
    def always_fails():
        calls["n"] += 1
        raise _TransientError()

    with pytest.raises(_TransientError):
        always_fails()
    assert calls["n"] == 2  # exactly max_attempts, no more


def test_sync_does_not_retry_non_transient_exceptions():
    calls = {"n": 0}

    @retry_transient(max_attempts=3, exceptions=(_TransientError,), backoff_seconds=0)
    def raises_wrong_type():
        calls["n"] += 1
        raise _NonTransientError("not retryable")

    with pytest.raises(_NonTransientError):
        raises_wrong_type()
    assert calls["n"] == 1  # no retry attempted


async def test_async_retries_and_succeeds_after_transient_failure():
    calls = {"n": 0}

    @retry_transient(max_attempts=3, exceptions=(_TransientError,), backoff_seconds=0)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _TransientError()
        return "async-ok"

    assert await flaky() == "async-ok"
    assert calls["n"] == 3


async def test_async_does_not_retry_non_transient_exceptions():
    calls = {"n": 0}

    @retry_transient(max_attempts=3, exceptions=(_TransientError,), backoff_seconds=0)
    async def raises_wrong_type():
        calls["n"] += 1
        raise _NonTransientError("not retryable")

    with pytest.raises(_NonTransientError):
        await raises_wrong_type()
    assert calls["n"] == 1
