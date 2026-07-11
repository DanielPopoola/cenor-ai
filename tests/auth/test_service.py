from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from auth.domain import User
from auth.errors import (
    GoogleOAuthExchangeError,
    InvalidOAuthStateError,
    InvalidSessionCookieError,
)
from auth.service import AuthService, OAuthStateStore
from config import Settings


def _extract_state(authorize_url: str) -> str:
    query = urlparse(authorize_url).query
    return parse_qs(query)["state"][0]


class FakeUserRepository:
    """In-memory stand-in for UserRepository — matches its method
    shapes exactly, no DB involved."""

    def __init__(self):
        self._by_id: dict[str, User] = {}
        self._by_google_sub: dict[str, User] = {}
        self._next_id = 1

    def find_by_id(self, user_id: str) -> User:
        if user_id not in self._by_id:
            from auth.errors import UserNotFoundError

            raise UserNotFoundError(user_id)
        return self._by_id[user_id]

    def find_by_google_sub(self, google_sub: str) -> User | None:
        return self._by_google_sub.get(google_sub)

    def create(self, email: str, name: str | None, google_sub: str) -> User:
        from datetime import datetime, timezone

        user = User(
            id=f"user-{self._next_id}",
            email=email,
            name=name,
            google_sub=google_sub,
            created_at=datetime.now(timezone.utc),
        )
        self._next_id += 1
        self._by_id[user.id] = user
        self._by_google_sub[google_sub] = user
        return user


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        google_client_id="cid",
        google_client_secret="csecret",
        cookie_signing_secret="sekrit",
    )


@pytest.fixture
def fake_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def service(settings, fake_repo) -> AuthService:
    return AuthService(settings, fake_repo, OAuthStateStore())


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


# --- CSRF state handling -------------------------------------------------


def test_authorize_url_includes_a_fresh_state(service: AuthService):
    url = service.build_google_authorize_url()
    assert "state=" in url
    assert "client_id=cid" in url


async def test_callback_rejects_unknown_state(service: AuthService):
    with pytest.raises(InvalidOAuthStateError):
        await service.handle_google_callback(code="any-code", state="never-issued")


async def test_callback_rejects_replayed_state(service: AuthService, settings):
    state = _extract_state(service.build_google_authorize_url())

    fake_profile = {"sub": "g-1", "email": "a@b.com", "name": "A"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        await service.handle_google_callback(code="code-1", state=state)

    # second attempt with the same (now-consumed) state must fail
    with pytest.raises(InvalidOAuthStateError):
        await service.handle_google_callback(code="code-2", state=state)


# --- Upsert behavior -------------------------------------------------------


async def test_callback_creates_new_user_on_first_login(service: AuthService, fake_repo):
    state = _extract_state(service.build_google_authorize_url())
    fake_profile = {"sub": "g-new", "email": "new@example.com", "name": "New"}

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        user = await service.handle_google_callback(code="c", state=state)

    assert user.email == "new@example.com"
    assert fake_repo.find_by_google_sub("g-new") is not None


async def test_callback_returns_existing_user_on_repeat_login(service: AuthService):
    fake_profile = {"sub": "g-existing", "email": "e@example.com", "name": "E"}

    async def do_login():
        state = _extract_state(service.build_google_authorize_url())
        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
            mock_instance.get.return_value = _mock_response(200, fake_profile)
            return await service.handle_google_callback(code="c", state=state)

    first = await do_login()
    second = await do_login()
    assert first.id == second.id


async def test_callback_raises_on_google_token_exchange_failure(service: AuthService):
    state = _extract_state(service.build_google_authorize_url())

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(401, {})
        with pytest.raises(GoogleOAuthExchangeError):
            await service.handle_google_callback(code="bad-code", state=state)


async def test_callback_raises_when_userinfo_missing_required_fields(service: AuthService):
    state = _extract_state(service.build_google_authorize_url())

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, {"email": "no-sub@example.com"})
        with pytest.raises(GoogleOAuthExchangeError):
            await service.handle_google_callback(code="c", state=state)


# --- Cookie signing / verification -----------------------------------------


def test_cookie_round_trip(service: AuthService):
    cookie = service.issue_cookie_value("user-42")
    assert service.verify_cookie_value(cookie) == "user-42"


def test_cookie_tampering_is_rejected(service: AuthService):
    cookie = service.issue_cookie_value("user-42")
    tampered = cookie[:-4] + "xxxx"
    with pytest.raises(InvalidSessionCookieError):
        service.verify_cookie_value(tampered)


def test_expired_cookie_is_rejected(settings, fake_repo):
    expired_settings = settings.model_copy(update={"cookie_max_age_seconds": -1})
    service = AuthService(expired_settings, fake_repo, OAuthStateStore())
    cookie = service.issue_cookie_value("user-42")
    with pytest.raises(InvalidSessionCookieError):
        service.verify_cookie_value(cookie)


def test_malformed_cookie_is_rejected(service: AuthService):
    with pytest.raises(InvalidSessionCookieError):
        service.verify_cookie_value("not-a-real-cookie-value")
