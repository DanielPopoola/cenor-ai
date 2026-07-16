import io
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from docx import Document

from candidate_profile.domain import CVStructured, GitHubStructured, Skill, WorkExperience


class FakeAIService:
    def __init__(self, cv_result=None, github_result=None):
        self._cv_result = cv_result
        self._github_result = github_result

    async def structure_cv(self, raw_text: str):
        return self._cv_result

    async def structure_github(self, raw_profile_data: dict):
        return self._github_result

    async def run_interviewer_turn(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_observer(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_feedback_synthesis(self, *a, **k):
        raise AssertionError("not exercised")


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


def _login(client) -> None:
    """Drives a mocked OAuth round-trip, leaves the client holding a
    valid session cookie — mirrors tests/auth/test_routes.py's helper."""
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    fake_profile = {"sub": "g-cp-1", "email": "cp-routes@example.com", "name": "CP"}
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


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --- auth boundary --------------------------------------------------------


def test_get_profile_without_login_returns_401(client):
    r = client.get("/api/v1/profile")
    assert r.status_code == 401


def test_upload_cv_without_login_returns_401(client):
    r = client.post("/api/v1/profile/cv", files={"file": ("resume.pdf", b"x", "application/pdf")})
    assert r.status_code == 401


# --- GET /profile -----------------------------------------------------


def test_get_profile_creates_lazily_and_returns_explicit_statuses(client):
    _login(client)
    r = client.get("/api/v1/profile")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["cv_status"] == "pending"
    assert body["github_status"] == "skipped"


# --- POST /profile/cv: HTTP-boundary validation -------------------------


def test_upload_cv_rejects_unsupported_extension(client):
    _login(client)
    r = client.post(
        "/api/v1/profile/cv", files={"file": ("resume.txt", b"hello", "text/plain")}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ValidationError"


def test_upload_cv_rejects_empty_file(client):
    _login(client)
    r = client.post(
        "/api/v1/profile/cv", files={"file": ("resume.pdf", b"", "application/pdf")}
    )
    assert r.status_code == 422


def test_upload_cv_rejects_oversized_file(client, app):
    _login(client)
    app.state.settings.cv_upload_max_bytes = 10  # tiny cap for this test
    r = client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.pdf", b"x" * 100, "application/pdf")},
    )
    assert r.status_code == 422
    assert "limit" in r.json()["error"]["message"].lower()


def test_upload_cv_rejects_missing_filename(client):
    _login(client)
    r = client.post(
        "/api/v1/profile/cv", files={"file": ("", b"content", "application/pdf")}
    )
    assert r.status_code == 422


# --- POST /profile/cv: happy path, fake AI service ----------------------


def test_upload_cv_success_returns_done_status(client, app):
    _login(client)
    good_cv = CVStructured(
        is_valid=True,
        work_experience=[WorkExperience(company="Acme", title="Eng", start_date="2020")],
        skills=[Skill(name="Python")],
    )
    app.state.ai_service = FakeAIService(cv_result=good_cv)

    r = client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.docx", _docx_bytes("Ada, Engineer, Python"), "application/octet-stream")},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["cv_status"] == "done"
    assert body["cv_structured"]["skills"][0]["name"] == "Python"


def test_upload_cv_when_ai_unavailable_returns_422(client, app):
    _login(client)
    app.state.ai_service = None

    r = client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.docx", _docx_bytes("content"), "application/octet-stream")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CVStructuringError"


# --- POST /profile/cv: HTMX fragment responses ---------------------------


def test_upload_cv_htmx_success_returns_cv_card_fragment(client, app):
    _login(client)
    good_cv = CVStructured(
        is_valid=True,
        work_experience=[WorkExperience(company="Acme", title="Eng", start_date="2020")],
        skills=[Skill(name="Python")],
    )
    app.state.ai_service = FakeAIService(cv_result=good_cv)

    r = client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.docx", _docx_bytes("Ada, Engineer, Python"), "application/octet-stream")},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="cv-card"' in r.text
    assert "CV received" in r.text


def test_upload_cv_htmx_success_also_oob_swaps_continue_button_to_enabled(client, app):
    _login(client)
    good_cv = CVStructured(
        is_valid=True,
        work_experience=[WorkExperience(company="Acme", title="Eng", start_date="2020")],
        skills=[Skill(name="Python")],
    )
    app.state.ai_service = FakeAIService(cv_result=good_cv)

    r = client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.docx", _docx_bytes("Ada, Engineer, Python"), "application/octet-stream")},
        headers={"HX-Request": "true"},
    )
    assert 'id="continue-button-region"' in r.text
    assert 'hx-swap-oob="true"' in r.text
    assert 'href="/dashboard"' in r.text  # enabled link, not the disabled span


def test_upload_cv_htmx_validation_failure_renders_alert_not_card(client):
    _login(client)
    r = client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.txt", b"hello", "text/plain")},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 422
    assert "text/html" in r.headers["content-type"]
    assert 'id="alert-region"' in r.text


# --- POST /profile/github: HTMX fragment responses ------------------------


def test_connect_github_htmx_returns_github_card_fragment(client, app):
    _login(client)
    good_github = GitHubStructured(is_valid=True, notable_repos=[])
    app.state.ai_service = FakeAIService(github_result=good_github)

    with patch(
        "candidate_profile.service.fetch_github_raw_profile",
        new=AsyncMock(
            return_value={"profile": {"created_at": "2020-01-01T00:00:00Z"}, "repos": []}
        ),
    ):
        r = client.post(
            "/api/v1/profile/github",
            data={"username": "adalovelace"},
            headers={"HX-Request": "true"},
        )
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="github-card"' in r.text
    assert "adalovelace" in r.text


# --- POST /profile/github: HTTP-boundary validation ----------------------


@pytest.mark.parametrize(
    "bad_username", ["-leading-hyphen", "trailing-hyphen-", "has spaces", "a" * 40]
)
def test_connect_github_rejects_malformed_usernames(client, bad_username):
    _login(client)
    r = client.post("/api/v1/profile/github", data={"username": bad_username})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ValidationError"


def test_connect_github_rejects_missing_username_field(client):
    """An empty/missing form field is caught by FastAPI's own request
    validation before it ever reaches our custom validator — still a
    422, just a different error code than a malformed-but-present
    username."""
    _login(client)
    r = client.post("/api/v1/profile/github", data={"username": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "RequestValidationError"


def test_connect_github_accepts_valid_username_shape(client, app):
    _login(client)
    app.state.ai_service = FakeAIService(
        github_result=GitHubStructured(is_valid=True, bio="hi")
    )
    with patch(
        "candidate_profile.service.fetch_github_raw_profile",
        new=AsyncMock(
            return_value={"profile": {"created_at": "2020-01-01T00:00:00Z"}, "repos": []}
        ),
    ):
        r = client.post("/api/v1/profile/github", data={"username": "octocat"})
    assert r.status_code == 200
    assert r.json()["data"]["github_status"] == "done"


def test_connect_github_failure_does_not_error_the_request(client, app):
    """The non-blocking rule holds at the HTTP layer too — a GitHub
    failure is still a 200 with github_status='failed', never a 5xx/4xx."""
    from candidate_profile.errors import GitHubFetchError

    _login(client)
    with patch(
        "candidate_profile.service.fetch_github_raw_profile",
        new=AsyncMock(side_effect=GitHubFetchError("not found")),
    ):
        r = client.post("/api/v1/profile/github", data={"username": "octocat"})
    assert r.status_code == 200
    assert r.json()["data"]["github_status"] == "failed"


def test_every_profile_response_carries_request_id_header(client):
    _login(client)
    r = client.get("/api/v1/profile")
    assert "x-request-id" in r.headers
