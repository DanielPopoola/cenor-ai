from fastapi import FastAPI

from app.exception_handlers import register_exception_handlers
from common.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from common.middleware import RequestIDMiddleware


def _build_test_app():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)

    @app.get("/notfound")
    def _notfound():
        raise NotFoundError("missing")

    @app.get("/validation")
    def _validation():
        raise ValidationError("bad input")

    @app.get("/conflict")
    def _conflict():
        raise ConflictError("already exists")

    @app.get("/unauthorized")
    def _unauthorized():
        raise UnauthorizedError("no access")

    @app.get("/subclass-notfound")
    def _subclass_notfound():
        class SessionNotFoundError(NotFoundError):
            pass

        raise SessionNotFoundError("session missing")

    @app.get("/unexpected")
    def _unexpected():
        raise RuntimeError("boom")

    return app


def _client():
    from fastapi.testclient import TestClient

    return TestClient(_build_test_app(), raise_server_exceptions=False)


def test_not_found_maps_to_404():
    r = _client().get("/notfound")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NotFoundError"


def test_validation_maps_to_422():
    r = _client().get("/validation")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ValidationError"


def test_conflict_maps_to_409():
    r = _client().get("/conflict")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ConflictError"


def test_unauthorized_maps_to_401():
    r = _client().get("/unauthorized")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UnauthorizedError"


def test_subclass_inherits_parent_family_status():
    """A domain-specific subclass (e.g. SessionNotFoundError) gets its
    parent family's status without redeclaring it."""
    r = _client().get("/subclass-notfound")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SessionNotFoundError"


def test_unhandled_exception_maps_to_500_generic_message():
    r = _client().get("/unexpected")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "InternalServerError"
    # never leak the raw exception message to the client
    assert "boom" not in body["error"]["message"]


def test_every_error_response_has_a_request_id():
    for path in ["/notfound", "/validation", "/conflict", "/unauthorized", "/unexpected"]:
        r = _client().get(path)
        assert r.json()["error"]["request_id"]
