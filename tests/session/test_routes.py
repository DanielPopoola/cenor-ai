from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from session.domain import InterviewerTurnResponse, SegmentChecklist


class FakeAIService:
    """Returns a queued sequence of InterviewerTurnResponses, one per
    call, mirroring tests/session/test_service.py's fake."""

    def __init__(self, responses: list):
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


def _fully_demonstrated():
    return InterviewerTurnResponse(
        next_question="",
        updated_checklist=SegmentChecklist(
            clarifies_ambiguity="demonstrated",
            reasons_through_examples="demonstrated",
            chooses_approach_intentionally="demonstrated",
            tests_and_catches_issues="demonstrated",
            communicates_thinking="demonstrated",
        ),
        segment_complete=True,
        reasoning="all behaviors demonstrated",
    )


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


def _login(client) -> None:
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    fake_profile = {"sub": "g-sess-1", "email": "sess-routes@example.com", "name": "S"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )


def _setup_complete_profile_and_job(client, app) -> str:
    """Uploads a CV that meets the completeness bar and creates a job
    posting. Returns the job_posting_id. Session creation is gated on
    both existing."""
    from candidate_profile.domain import CVStructured, Skill, WorkExperience

    app.state.ai_service = _CVFakeAIService(
        CVStructured(
            is_valid=True,
            work_experience=[WorkExperience(company="Acme", title="Eng", start_date="2020")],
            skills=[Skill(name="Python")],
        )
    )
    import io
    from docx import Document

    doc = Document()
    doc.add_paragraph("Ada Lovelace, Software Engineer, Python")
    buf = io.BytesIO()
    doc.save(buf)
    client.post(
        "/api/v1/profile/cv",
        files={"file": ("resume.docx", buf.getvalue(), "application/octet-stream")},
    )

    job_resp = client.post(
        "/api/v1/jobs", json={"title": "Backend Engineer", "description_raw": "Build things"}
    )
    return job_resp.json()["data"]["id"]


class _CVFakeAIService:
    """Minimal fake used only for the CV-upload setup step above."""

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


# --- auth boundary --------------------------------------------------------


def test_create_session_without_login_returns_401(client):
    r = client.post("/api/v1/sessions", json={"job_posting_id": "x"})
    assert r.status_code == 401


def test_list_sessions_without_login_returns_401(client):
    r = client.get("/api/v1/sessions")
    assert r.status_code == 401


# --- create_session: gating ------------------------------------------------


def test_create_session_blocked_without_complete_profile(client):
    _login(client)
    job_resp = client.post(
        "/api/v1/jobs", json={"title": "Eng", "description_raw": "desc"}
    )
    job_id = job_resp.json()["data"]["id"]

    r = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CandidateProfileIncompleteError"


def test_create_session_rejects_invalid_duration(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress()])

    r = client.post(
        "/api/v1/sessions", json={"job_posting_id": job_id, "duration_limit_minutes": 999}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ValidationError"


def test_create_session_rejects_missing_job_posting_id(client):
    _login(client)
    r = client.post("/api/v1/sessions", json={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "RequestValidationError"


# --- full lifecycle --------------------------------------------------------


def test_create_session_success_returns_first_question(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("What would you clarify first?")])

    r = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["outcome"] == "continue"
    assert body["next_question"] == "What would you clarify first?"
    assert body["segment"]["segment_order"] == 0
    assert body["session"]["status"] == "in_progress"
    # checklist must never appear in the response — invisible machinery
    assert "checklist" not in body["segment"]


def test_submit_turn_returns_follow_up_question(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("opening"), _in_progress("follow-up")])

    create_resp = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    session_id = create_resp.json()["data"]["session"]["id"]

    r = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json={"content": "I would clarify the input size first"},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["outcome"] == "continue"
    assert body["next_question"] == "follow-up"


def test_submit_turn_rejects_empty_content(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("opening")])
    create_resp = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    session_id = create_resp.json()["data"]["session"]["id"]

    r = client.post(f"/api/v1/sessions/{session_id}/turns", json={"content": ""})
    assert r.status_code == 422


def test_segment_transition_then_next_question_flow(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService(
        [_in_progress("opening"), _fully_demonstrated(), _in_progress("segment 2 opener")]
    )

    create_resp = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    session_id = create_resp.json()["data"]["session"]["id"]

    turn_resp = client.post(
        f"/api/v1/sessions/{session_id}/turns", json={"content": "an answer"}
    )
    assert turn_resp.status_code == 200
    turn_body = turn_resp.json()["data"]
    assert turn_body["outcome"] == "segment_transitioned"
    assert turn_body["next_question"] is None

    next_resp = client.post(f"/api/v1/sessions/{session_id}/next-question")
    assert next_resp.status_code == 200
    next_body = next_resp.json()["data"]
    assert next_body["outcome"] == "continue"
    assert next_body["next_question"] == "segment 2 opener"
    assert next_body["segment"]["segment_order"] == 1


def test_end_session_marks_completed(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("opening")])
    create_resp = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    session_id = create_resp.json()["data"]["session"]["id"]

    r = client.post(f"/api/v1/sessions/{session_id}/end")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "completed"


def test_get_session_returns_owned_session(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("opening")])
    create_resp = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    session_id = create_resp.json()["data"]["session"]["id"]

    r = client.get(f"/api/v1/sessions/{session_id}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == session_id


def test_get_session_not_found_returns_404(client):
    _login(client)
    r = client.get("/api/v1/sessions/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SessionNotFoundError"


def test_list_sessions_returns_only_own_sessions(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("opening")])
    client.post("/api/v1/sessions", json={"job_posting_id": job_id})

    r = client.get("/api/v1/sessions")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1


def test_submit_turn_after_session_ended_returns_422(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("opening")])
    create_resp = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    session_id = create_resp.json()["data"]["session"]["id"]
    client.post(f"/api/v1/sessions/{session_id}/end")

    r = client.post(f"/api/v1/sessions/{session_id}/turns", json={"content": "too late"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SessionNotInProgressError"
