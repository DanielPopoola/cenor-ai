from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse


def _extract_state(location_header: str) -> str:
    query = urlparse(location_header).query
    return parse_qs(query)["state"][0]


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


def test_google_login_redirects_to_google(client):
    r = client.get("/api/v1/auth/google", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://accounts.google.com/")


def test_me_without_cookie_returns_401_envelope(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    body = r.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "InvalidSessionCookieError"
    assert body["error"]["request_id"]  # non-empty


def _login(client) -> dict:
    """Drives a full mocked OAuth round-trip, returns the JSON body of
    the resulting /me call."""
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = _extract_state(login_resp.headers["location"])

    fake_profile = {"sub": "g-route-1", "email": "route@example.com", "name": "Route"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        callback_resp = client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )
    assert callback_resp.status_code == 302
    assert "set-cookie" in callback_resp.headers
    return client.get("/api/v1/auth/me").json()


def test_full_login_flow_then_me_returns_user_envelope(client):
    body = _login(client)
    assert body["success"] is True
    assert body["data"]["email"] == "route@example.com"
    assert body["error"] is None


def test_logout_clears_session(client):
    _login(client)

    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["data"] == {"logged_out": True}

    me_after = client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


def test_logout_sets_hx_redirect_to_landing_page(client):
    _login(client)

    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.headers["hx-redirect"] == "/"


def test_callback_with_invalid_state_returns_422_envelope(client):
    r = client.get("/api/v1/auth/google/callback?code=x&state=never-issued")
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "InvalidOAuthStateError"


def test_every_response_carries_request_id_header(client):
    r = client.get("/api/v1/auth/me")
    assert "x-request-id" in r.headers
    # header and envelope's embedded request_id must match
    assert r.headers["x-request-id"] == r.json()["error"]["request_id"]


def _callback(client, google_sub: str, email: str):
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = _extract_state(login_resp.headers["location"])

    fake_profile = {"sub": google_sub, "email": email, "name": "Route"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        return client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )


def test_first_time_user_redirected_to_onboarding(client):
    callback_resp = _callback(client, "g-new-user", "newuser@example.com")
    assert callback_resp.status_code == 302
    assert callback_resp.headers["location"] == "/onboarding"


def test_returning_user_with_completed_cv_redirected_to_dashboard(client, app):
    from candidate_profile.domain import CVStructured, Skill, WorkExperience
    from tests.candidate_profile.test_routes import FakeAIService, _docx_bytes

    app.state.ai_service = FakeAIService(
        cv_result=CVStructured(
            is_valid=True,
            work_experience=[WorkExperience(company="Acme", title="Eng", start_date="2020")],
            skills=[Skill(name="Python")],
        )
    )
    # First login creates the account and uploads a CV
    _callback(client, "g-returning-user", "returning@example.com")
    client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.docx", _docx_bytes("Ada, Engineer"), "application/octet-stream")},
    )
    client.post("/api/v1/auth/logout")

    # Second login for the same google_sub should skip onboarding
    callback_resp = _callback(client, "g-returning-user", "returning@example.com")
    assert callback_resp.status_code == 302
    assert callback_resp.headers["location"] == "/dashboard"
