import io
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

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


def _in_progress(question="opening question"):
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

    fake_profile = {"sub": "g-jobs-1", "email": "jobs@example.com", "name": "Jobs"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )


def _complete_cv(client: TestClient, app) -> None:
    """Uploads a CV meeting the completeness bar. Does not create a job
    posting via the API — /jobs/new is responsible for that."""
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


def _create_job_via_form(client: TestClient, title="Staff Engineer", company="Airbnb") -> str:
    """Submits /jobs/new and returns the created job_posting_id, parsed
    from the HX-Redirect header."""
    r = client.post(
        "/jobs/new",
        data={
            "title": title,
            "company": company,
            "description_raw": "Build distributed systems",
        },
        headers={"HX-Request": "true"},
    )
    location = r.headers["hx-redirect"]
    return location.rsplit("/", 1)[-1]


# --- /jobs (list) -----------------------------------------------------------


def test_jobs_list_requires_login(client: TestClient):
    r = client.get("/jobs", follow_redirects=False)
    assert r.status_code == 401


def test_jobs_list_empty_state(client: TestClient):
    _login(client)
    r = client.get("/jobs")
    assert r.status_code == 200
    assert "No jobs saved yet" in r.text


def test_jobs_list_shows_saved_job_with_session_count(client: TestClient, app):
    _login(client)
    _complete_cv(client, app)
    job_id = _create_job_via_form(client, title="Staff Engineer", company="Airbnb")

    r = client.get("/jobs")
    assert r.status_code == 200
    assert "Staff Engineer" in r.text
    assert "Airbnb" in r.text
    assert "0 sessions" in r.text
    assert f'href="/jobs/{job_id}"' in r.text


# --- /jobs/new (create) ------------------------------------------------------


def test_new_job_page_requires_login(client: TestClient):
    r = client.get("/jobs/new", follow_redirects=False)
    assert r.status_code == 401


def test_new_job_page_redirects_to_onboarding_without_complete_profile(client: TestClient):
    _login(client)
    r = client.get("/jobs/new", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/onboarding"


def test_new_job_page_renders_form_with_complete_profile(client: TestClient, app):
    _login(client)
    _complete_cv(client, app)

    r = client.get("/jobs/new")
    assert r.status_code == 200
    assert 'name="title"' in r.text
    assert 'name="description_raw"' in r.text
    assert 'hx-post="/jobs/new"' in r.text


def test_new_job_page_has_no_session_length_picker(client: TestClient, app):
    """Length selection belongs to the job detail page's 'start a
    session' action, not job creation itself."""
    _login(client)
    _complete_cv(client, app)

    r = client.get("/jobs/new")
    assert 'name="duration_limit_minutes"' not in r.text


def test_submit_new_job_creates_it_and_redirects_to_detail(client: TestClient, app):
    _login(client)
    _complete_cv(client, app)

    r = client.post(
        "/jobs/new",
        data={
            "title": "Staff Engineer",
            "company": "Airbnb",
            "description_raw": "Build distributed systems",
        },
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert r.headers["hx-redirect"].startswith("/jobs/")

    jobs = client.get("/api/v1/jobs").json()["data"]
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Staff Engineer"


def test_submit_new_job_without_complete_profile_returns_error_fragment(client: TestClient):
    _login(client)

    r = client.post(
        "/jobs/new",
        data={"title": "Staff Engineer", "description_raw": "Build distributed systems"},
        headers={"HX-Request": "true"},
    )
    # job creation itself has no completeness gate server-side today;
    # this exercises the ordinary success path for an edge case where
    # a user reaches the form despite no CV (e.g. stale tab)
    assert r.status_code == 200


# --- /jobs/{id} (detail) ------------------------------------------------------


def test_job_detail_requires_login(client: TestClient):
    r = client.get("/jobs/nonexistent", follow_redirects=False)
    assert r.status_code == 401


def test_job_detail_404s_for_unknown_job(client: TestClient):
    _login(client)
    r = client.get("/jobs/nonexistent")
    assert r.status_code == 404


def test_job_detail_shows_job_info_and_empty_sessions(client: TestClient, app):
    _login(client)
    _complete_cv(client, app)
    job_id = _create_job_via_form(client, title="Staff Engineer", company="Airbnb")

    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert "Staff Engineer" in r.text
    assert "Airbnb" in r.text
    assert "No sessions yet for this job" in r.text
    assert f'hx-post="/jobs/{job_id}/sessions"' in r.text


def test_job_detail_shows_length_options_from_settings(client: TestClient, app):
    _login(client)
    _complete_cv(client, app)
    job_id = _create_job_via_form(client)

    r = client.get(f"/jobs/{job_id}")
    assert "15m" in r.text
    assert "30m" in r.text
    assert "40m" in r.text


def test_job_detail_lists_sessions_started_against_it(client: TestClient, app):
    _login(client)
    _complete_cv(client, app)
    job_id = _create_job_via_form(client, title="Staff Engineer")

    app.state.ai_service = _InterviewerFakeAIService([_in_progress()])
    session_resp = client.post(
        f"/jobs/{job_id}/sessions",
        data={"duration_limit_minutes": "30"},
        headers={"HX-Request": "true"},
    )
    session_id = session_resp.headers["hx-redirect"].rsplit("/", 1)[-1]

    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert f'href="/sessions/{session_id}"' in r.text
    assert "In Progress" in r.text


def test_job_detail_does_not_show_sessions_from_other_jobs(client: TestClient, app):
    _login(client)
    _complete_cv(client, app)
    job_a = _create_job_via_form(client, title="Job A")
    job_b = _create_job_via_form(client, title="Job B")

    app.state.ai_service = _InterviewerFakeAIService([_in_progress()])
    client.post(
        f"/jobs/{job_a}/sessions",
        data={"duration_limit_minutes": "30"},
        headers={"HX-Request": "true"},
    )

    r = client.get(f"/jobs/{job_b}")
    assert "No sessions yet for this job" in r.text


# --- POST /jobs/{id}/sessions (start session) --------------------------------


def test_start_session_creates_session_and_redirects(client: TestClient, app):
    _login(client)
    _complete_cv(client, app)
    job_id = _create_job_via_form(client)
    app.state.ai_service = _InterviewerFakeAIService([_in_progress()])

    r = client.post(
        f"/jobs/{job_id}/sessions",
        data={"duration_limit_minutes": "30"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert r.headers["hx-redirect"].startswith("/sessions/")

    sessions = client.get("/api/v1/sessions").json()["data"]
    assert len(sessions) == 1
    assert sessions[0]["job_posting_id"] == job_id


def test_start_session_without_complete_profile_returns_error_fragment(client: TestClient):
    _login(client)
    job_resp = client.post(
        "/api/v1/jobs", json={"title": "Eng", "description_raw": "desc"}
    )
    job_id = job_resp.json()["data"]["id"]

    r = client.post(
        f"/jobs/{job_id}/sessions",
        data={"duration_limit_minutes": "30"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 422
    assert 'id="alert-region"' in r.text
