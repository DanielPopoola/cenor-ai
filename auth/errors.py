from common.errors import NotFoundError, UnauthorizedError, ValidationError


class UserNotFoundError(NotFoundError):
    pass


class InvalidOAuthStateError(ValidationError):
    """The state param on OAuth callback didn't match what was issued,
    or had already expired — CSRF protection failing closed."""


class InvalidSessionCookieError(UnauthorizedError):
    """Cookie missing, signature invalid, or expired."""


class GoogleOAuthExchangeError(ValidationError):
    """Google's token/userinfo exchange failed or returned unusable data."""
