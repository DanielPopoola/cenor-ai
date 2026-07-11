import base64
import hashlib
import hmac
import json
import secrets
import time


import httpx

from auth.errors import (
    GoogleOAuthExchangeError,
    InvalidOAuthStateError,
    InvalidSessionCookieError,
)
from auth.domain import User
from auth.repository import UserRepository
from config import Settings
from common.logger import get_logger

_log = get_logger("auth.service")

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class OAuthStateStore:
    """
    In-memory, short-TTL store for the CSRF `state` param — mirrors
    shared/rate_limit.py's in-memory pattern. Doesn't need to survive a
    restart (a restart mid-OAuth-flow just means the user retries
    login), and a DB table for a few-minutes-TTL value would be
    disproportionate infrastructure for what it's protecting.
    """

    def __init__(self):
        self._states: dict[str, float] = {}  # state -> expires_at epoch

    def issue(self, ttl_seconds: int) -> str:
        state = secrets.token_urlsafe(32)
        self._states[state] = time.time() + ttl_seconds
        return state

    def consume(self, state: str) -> bool:
        """Returns True and discards the state if valid+unexpired.
        One-time use: a state can't be replayed even within its TTL."""
        expires_at = self._states.pop(state, None)
        if expires_at is None:
            return False
        return time.time() < expires_at


class AuthService:
    def __init__(
        self,
        settings: Settings,
        repository: UserRepository,
        state_store: OAuthStateStore,
    ):
        self._settings = settings
        self._repository = repository
        self._state_store = state_store

    def build_google_authorize_url(self) -> str:
        state = self._state_store.issue(self._settings.oauth_state_ttl_seconds)
        params = {
            "client_id": self._settings.google_client_id,
            "redirect_uri": self._settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{_GOOGLE_AUTH_URL}?{query}"

    async def handle_google_callback(self, code: str, state: str) -> User:
        if not self._state_store.consume(state):
            raise InvalidOAuthStateError(
                "OAuth state missing, expired, or already used"
            )

        google_profile = await self._exchange_code_for_profile(code)

        existing = self._repository.find_by_google_sub(google_profile["sub"])
        if existing is not None:
            return existing

        return self._repository.create(
            email=google_profile["email"],
            name=google_profile.get("name"),
            google_sub=google_profile["sub"],
        )

    async def _exchange_code_for_profile(self, code: str) -> dict:
        async with httpx.AsyncClient(
            timeout=self._settings.llm_request_timeout_seconds
        ) as client:
            token_resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._settings.google_client_id,
                    "client_secret": self._settings.google_client_secret,
                    "redirect_uri": self._settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                raise GoogleOAuthExchangeError(
                    f"Google token exchange failed: {token_resp.status_code}"
                )
            access_token = token_resp.json().get("access_token")
            if not access_token:
                raise GoogleOAuthExchangeError(
                    "Google token response missing access_token"
                )

            userinfo_resp = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                raise GoogleOAuthExchangeError(
                    f"Google userinfo fetch failed: {userinfo_resp.status_code}"
                )
            profile = userinfo_resp.json()
            if "sub" not in profile or "email" not in profile:
                raise GoogleOAuthExchangeError(
                    "Google userinfo response missing required fields"
                )
            return profile

    # --- Cookie signing / verification -----------------------------------
    # Payload: base64url(json({user_id, expires_at})) + "." + hex(hmac)
    # Stateless: verification is a signature check, no DB lookup, per
    # the TDD's deliberate no-session-table tradeoff.

    def issue_cookie_value(self, user_id: str) -> str:
        expires_at = int(time.time()) + self._settings.cookie_max_age_seconds
        payload = {"user_id": user_id, "expires_at": expires_at}
        return self._sign(payload)

    def verify_cookie_value(self, cookie_value: str) -> str:
        """Returns the user_id if the cookie is validly signed and
        unexpired, else raises InvalidSessionCookieError."""
        try:
            encoded_payload, signature_hex = cookie_value.rsplit(".", 1)
        except ValueError as e:
            raise InvalidSessionCookieError("Malformed cookie") from e

        expected_signature = self._compute_signature(encoded_payload)
        if not hmac.compare_digest(signature_hex, expected_signature):
            raise InvalidSessionCookieError("Cookie signature mismatch")

        try:
            payload = json.loads(base64.urlsafe_b64decode(encoded_payload.encode()))
        except (ValueError, UnicodeDecodeError) as e:
            raise InvalidSessionCookieError("Malformed cookie payload") from e

        if payload.get("expires_at", 0) < time.time():
            raise InvalidSessionCookieError("Cookie expired")

        user_id = payload.get("user_id")
        if not user_id:
            raise InvalidSessionCookieError("Cookie payload missing user_id")
        return user_id

    def _sign(self, payload: dict) -> str:
        encoded_payload = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode()
        signature = self._compute_signature(encoded_payload)
        return f"{encoded_payload}.{signature}"

    def _compute_signature(self, encoded_payload: str) -> str:
        return hmac.new(
            self._settings.cookie_signing_secret.encode(),
            encoded_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
