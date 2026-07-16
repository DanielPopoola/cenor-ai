from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


def _login(client: TestClient) -> None:
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    fake_profile = {"sub": "g-web-1", "email": "web-routes@example.com", "name": "Web"}
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


def test_onboarding_requires_login(client: TestClient):
    r = client.get("/onboarding", follow_redirects=False)
    assert r.status_code == 401


def test_onboarding_fresh_user_shows_disabled_continue(client: TestClient):
    _login(client)
    r = client.get("/onboarding")
    assert r.status_code == 200
    assert "Drag and drop your PDF" in r.text
    assert "cursor-not-allowed" in r.text  # disabled Continue span, not a real link


def test_onboarding_after_cv_upload_shows_enabled_continue(client: TestClient, app):
    from candidate_profile.domain import CVStructured, Skill, WorkExperience
    from tests.candidate_profile.test_routes import FakeAIService, _docx_bytes

    _login(client)
    app.state.ai_service = FakeAIService(
        cv_result=CVStructured(
            is_valid=True,
            work_experience=[WorkExperience(company="Acme", title="Eng", start_date="2020")],
            skills=[Skill(name="Python")],
        )
    )
    client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.docx", _docx_bytes("Ada, Engineer"), "application/octet-stream")},
    )

    r = client.get("/onboarding")
    assert r.status_code == 200
    assert "CV received" in r.text
    assert 'href="/dashboard"' in r.text


def test_auth_page_returns_html(client: TestClient):
    response = client.get("/auth")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_auth_page_omits_authenticated_nav_for_anonymous_visitor(client: TestClient):
    response = client.get("/auth")

    assert "Dashboard" not in response.text
    assert "New Session" not in response.text


def test_auth_page_links_to_google_oauth(client: TestClient):
    response = client.get("/auth")

    assert 'href="/api/v1/auth/google"' in response.text


def test_static_stylesheet_serves(client: TestClient):
    response = client.get("/static/css/output.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
