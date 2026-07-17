from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

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


class FakeAIService:
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


def _login(client: TestClient) -> None:
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    fake_profile = {"sub": "g-interview-1", "email": "interview@example.com", "name": "I"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )


def _setup_complete_profile_and_job(client: TestClient, app) -> str:
    import io

    from docx import Document

    from candidate_profile.domain import CVStructured, Skill, WorkExperience

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
    job_resp = client.post(
        "/api/v1/jobs", json={"title": "Staff Engineer", "description_raw": "Build things"}
    )
    return job_resp.json()["data"]["id"]


def _start_session(client: TestClient, job_id: str) -> str:
    resp = client.post("/api/v1/sessions", json={"job_posting_id": job_id})
    return resp.json()["data"]["session"]["id"]


def test_interview_page_requires_login(client: TestClient):
    r = client.get("/sessions/nonexistent", follow_redirects=False)
    assert r.status_code == 401


def test_interview_page_404s_for_unknown_session(client: TestClient):
    _login(client)
    r = client.get("/sessions/nonexistent")
    assert r.status_code == 404


def test_interview_page_renders_current_question_and_editor_for_coding_segment(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("Implement an LRU cache")])
    session_id = _start_session(client, job_id)

    r = client.get(f"/sessions/{session_id}")
    assert r.status_code == 200
    assert "Implement an LRU cache" in r.text
    assert 'name="code_snapshot"' in r.text
    assert "Section 1 of 4" in r.text
    assert "Programming" in r.text


def test_interview_page_omits_editor_for_conversational_segment(client, app):
    """After the first segment transitions, frameworks_tools has no
    editor — the shell must not show a code pane there."""
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("q0"), _fully_demonstrated()])
    session_id = _start_session(client, job_id)
    client.post(f"/api/v1/sessions/{session_id}/turns", json={"content": "answer"})

    app.state.ai_service = FakeAIService([_in_progress("q1")])
    client.post(f"/api/v1/sessions/{session_id}/next-question")

    r = client.get(f"/sessions/{session_id}")
    assert r.status_code == 200
    assert 'name="code_snapshot"' not in r.text
    assert "Section 2 of 4" in r.text


def test_interview_page_redirects_completed_session_to_feedback(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress()])
    session_id = _start_session(client, job_id)
    client.post(f"/api/v1/sessions/{session_id}/end")

    r = client.get(f"/sessions/{session_id}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == f"/sessions/{session_id}/feedback"


def test_submit_turn_htmx_continue_returns_turn_fragment(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("q0")])
    session_id = _start_session(client, job_id)

    app.state.ai_service = FakeAIService([_in_progress("Now consider concurrent access")])
    r = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"content": "my answer", "code_snapshot": "def f(): pass"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Now consider concurrent access" in r.text
    assert 'id="turn-region"' in r.text


def test_submit_turn_htmx_segment_transition_returns_interstitial(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress("q0")])
    session_id = _start_session(client, job_id)

    app.state.ai_service = FakeAIService([_fully_demonstrated()])
    r = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"content": "final answer for this segment"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Moving to the next section" in r.text
    assert f'hx-post="/sessions/{session_id}/next-question"' in r.text
    assert "Frameworks" in r.text


def test_submit_turn_htmx_session_completed_sets_hx_redirect_to_feedback(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)

    responses = [_in_progress("open 0")]
    for i in range(4):
        responses.append(_fully_demonstrated())
        if i < 3:
            responses.append(_in_progress(f"open {i + 1}"))
    app.state.ai_service = FakeAIService(responses)

    session_id = _start_session(client, job_id)

    result = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"content": "answer 0"},
        headers={"HX-Request": "true"},
    )
    for _ in range(3):
        assert "Moving to the next section" in result.text
        client.post(f"/api/v1/sessions/{session_id}/next-question", headers={"HX-Request": "true"})
        result = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            data={"content": "next answer"},
            headers={"HX-Request": "true"},
        )

    assert result.status_code == 200
    assert result.headers["hx-redirect"] == f"/sessions/{session_id}/feedback"


def test_end_session_htmx_redirects_to_feedback(client, app):
    _login(client)
    job_id = _setup_complete_profile_and_job(client, app)
    app.state.ai_service = FakeAIService([_in_progress()])
    session_id = _start_session(client, job_id)

    r = client.post(
        f"/api/v1/sessions/{session_id}/end",
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert r.headers["hx-redirect"] == f"/sessions/{session_id}/feedback"
