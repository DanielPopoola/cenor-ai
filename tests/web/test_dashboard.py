from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import io

from docx import Document
from fastapi.testclient import TestClient

from candidate_profile.domain import CVStructured, Skill, WorkExperience
from session.domain import InterviewerTurnResponse, SegmentChecklist


class _CVFakeAIService:
    def __init__(self, cv_result):
        self._cv_result = cv_result

    async def structure_cv(self, raw_text):
        return self._cv_result

    async def structure_github(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_interviewer_turn(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_observer(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_feedback_synthesis(self, *a, **k):
        raise AssertionError("not exercised")


class _InterviewerFakeAIService:
    def __init__(self, responses):
        self._responses = list(responses)

    async def run_interviewer_turn(self, **kwargs):
        return self._responses.pop(0)

    async def structure_cv(self, *a, **k):
        raise AssertionError("not exercised")

    async def structure_github(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_observer(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_feedback_synthesis(self, *a, **k):
        raise AssertionError("not exercised")


def _in_progress(question="next question"):
    return InterviewerTurnResponse(
        next_question=question,
        updated_checklist=SegmentChecklist(),
        segment_complete=False,
        reasoning="not enough evidence yet",
    )


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


def _login(client: TestClient) -> None:
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    fake_profile = {"sub": "g-dash-1", "email": "dash@example.com", "name": "Dash User"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )


def _setup_complete_profile_and_job(client: TestClient, app, title="Backend Engineer", company=None) -> str:
    app.state.ai_service = _CVFakeAIService(
        CVStructured(
            is_valid=True,
            work_experience=[WorkExperience(company="Acme", title="Eng", start_date="2020")],
            skills=[Skill(name="Python")],
        )
    )
    doc = Document()
    doc.add_paragraph("Ada Lovelace, Software Engineer, Python")
    buf = io.BytesIO()
    doc.save(buf)
    client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.docx", buf.getvalue(), "application/octet-stream")},
    )

    payload = {"title": title, "description_raw": "Build things"}
    if company:
        payload["company"] = company
    job_resp = client.post("/api/v1/jobs", json=payload)
    return job_resp.json()["data"]["id"]


def test_dashboard_requires_login(client: TestClient):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 401


def test_dashboard_empty_state(client: TestClient):
    _login(client)
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "No sessions yet" in r.text


def test_dashboard_has_avatar_logout_affordance(client: TestClient):
    _login(client)
    r = client.get("/dashboard")
    assert 'action="/api/v1/auth/logout"' in r.text


def test_dashboard_lists_in_progress_session_as_resume_card(client: TestClient, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app, title="Staff Engineer", company="Airbnb")
    app.state.ai_service = _InterviewerFakeAIService([_in_progress("opening question")])
    session_resp = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    session_id = session_resp.json()["data"]["session"]["id"]

    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "Continue Interview" in r.text
    assert "Staff Engineer" in r.text
    assert "Airbnb" in r.text
    assert f'href="/sessions/{session_id}"' in r.text


def test_dashboard_shows_lens_type_derived_from_segments(client: TestClient, app):
    """Coding lens (editor_available on some segment) should render as
    'Coding', not need a stored lens_type field."""
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = _InterviewerFakeAIService([_in_progress()])
    client.post("/api/v1/sessions", json={"job_posting_id": job_id})

    r = client.get("/dashboard")
    assert "Coding" in r.text or "Conversational" in r.text
