from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from auth.models import UserORM
from candidate_profile.domain import CVStructured, Skill
from candidate_profile.models import CandidateProfileORM
from feedback.repository import FeedbackRepository
from feedback.domain import FocusPoint, TraitSummary
from job_posting.models import JobPostingORM
from observation.repository import ObservationRepository
from observation.domain import ObservationEntry
from session.domain import SegmentChecklist
from session.models import SegmentORM, SessionORM, TurnORM


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


def _login(client, email="fb-routes@example.com") -> None:
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    fake_profile = {"sub": f"g-{email}", "email": email, "name": "FB"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )


def _seed_completed_session(db_session, user_email: str) -> tuple[str, str]:
    """Completed session, one segment, one turn, plus a minimal
    CandidateProfile with cv_structured set — needed since
    FeedbackService looks up the profile for resource-relevance
    context (degrades gracefully if absent, but seeding one here keeps
    these tests closer to a real flow)."""
    user = db_session.query(UserORM).filter_by(email=user_email).first()

    profile = CandidateProfileORM(
        user_id=user.id,
        cv_attempted=True,
        cv_structured=CVStructured(
            is_valid=True, skills=[Skill(name="Python")]
        ).model_dump_json(),
    )
    db_session.add(profile)

    job = JobPostingORM(user_id=user.id, title="Eng", description_raw="desc")
    db_session.add(job)
    db_session.flush()

    session = SessionORM(
        user_id=user.id, job_posting_id=job.id, duration_limit_minutes=30,
        status="completed", ended_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    db_session.flush()

    segment = SegmentORM(
        session_id=session.id, segment_order=0, area="system_design",
        editor_available=False, duration_limit_minutes=10,
        checklist=SegmentChecklist().model_dump_json(), status="completed",
    )
    db_session.add(segment)
    db_session.flush()

    turn = TurnORM(segment_id=segment.id, turn_number=1, speaker="interviewer", content="Q1")
    db_session.add(turn)
    db_session.flush()
    db_session.commit()
    return user.id, session.id


def _seed_in_progress_session(db_session, user_email: str) -> tuple[str, str]:
    user = db_session.query(UserORM).filter_by(email=user_email).first()
    job = JobPostingORM(user_id=user.id, title="Eng", description_raw="desc")
    db_session.add(job)
    db_session.flush()

    session = SessionORM(user_id=user.id, job_posting_id=job.id, duration_limit_minutes=30)
    db_session.add(session)
    db_session.flush()
    db_session.commit()
    return user.id, session.id


class _FakeFeedbackAIService:
    def __init__(self, trait_summary=None, focus_points=None, raises=None):
        self._trait_summary = trait_summary or []
        self._focus_points = focus_points or []
        self._raises = raises
        self.call_count = 0

    async def run_feedback_synthesis(self, observations, lens_type, trait_mapping, candidate_profile_summary):
        from feedback.domain import FeedbackResult

        self.call_count += 1
        if self._raises is not None:
            raise self._raises
        return FeedbackResult(trait_summary=self._trait_summary, focus_points=self._focus_points)

    async def structure_cv(self, *a, **k):
        raise AssertionError("not exercised")

    async def structure_github(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_interviewer_turn(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_observer(self, *a, **k):
        raise AssertionError("not exercised")


# --- basic auth / tenant isolation --------------------------------------


def test_get_feedback_without_login_returns_401(client):
    r = client.get("/api/v1/sessions/some-id/feedback")
    assert r.status_code == 401


def test_get_feedback_returns_404_for_session_belonging_to_another_user(client, db_session):
    _login(client)
    other_user = UserORM(email="other-fb@example.com", name="Other", google_sub="other-fb-sub")
    db_session.add(other_user)
    db_session.flush()
    other_job = JobPostingORM(user_id=other_user.id, title="Eng", description_raw="d")
    db_session.add(other_job)
    db_session.flush()
    other_session = SessionORM(user_id=other_user.id, job_posting_id=other_job.id, duration_limit_minutes=30)
    db_session.add(other_session)
    db_session.flush()
    db_session.commit()

    r = client.get(f"/api/v1/sessions/{other_session.id}/feedback")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SessionNotFoundError"


# --- too-early cases -----------------------------------------------------


def test_get_feedback_returns_404_when_observation_does_not_exist_yet(client, app, db_session):
    """Feedback can't run before Observation exists at all — this must
    stay a plain 404, no self-healing attempted."""
    _login(client)
    _, session_id = _seed_in_progress_session(db_session, "fb-routes@example.com")

    fake_ai = _FakeFeedbackAIService()
    app.state.ai_service = fake_ai

    r = client.get(f"/api/v1/sessions/{session_id}/feedback")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FeedbackNotFoundError"
    assert fake_ai.call_count == 0


def test_get_feedback_returns_404_when_session_in_progress_even_with_observation(client, app, db_session):
    """Belt-and-suspenders: even if an Observation somehow exists for
    an in_progress session, Feedback must not self-heal until the
    session has actually ended."""
    _login(client)
    _, session_id = _seed_in_progress_session(db_session, "fb-routes@example.com")

    ObservationRepository(db_session).create(session_id=session_id, entries=[])
    db_session.commit()

    fake_ai = _FakeFeedbackAIService()
    app.state.ai_service = fake_ai

    r = client.get(f"/api/v1/sessions/{session_id}/feedback")
    assert r.status_code == 404
    assert fake_ai.call_count == 0


# --- happy path ----------------------------------------------------------


def test_get_feedback_returns_existing_feedback(client, db_session):
    _login(client)
    _, session_id = _seed_completed_session(db_session, "fb-routes@example.com")

    ObservationRepository(db_session).create(session_id=session_id, entries=[])
    FeedbackRepository(db_session).create(
        session_id=session_id,
        trait_summary=[
            TraitSummary(trait="problem_solving", summary="did X this session", source_observations=[1])
        ],
        focus_points=[
            FocusPoint(pattern="pattern Y", resource="topic area Z", source_observations=[2])
        ],
    )
    db_session.commit()

    r = client.get(f"/api/v1/sessions/{session_id}/feedback")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["session_id"] == session_id
    assert body["trait_summary"][0]["trait"] == "problem_solving"
    assert body["focus_points"][0]["resource"] == "topic area Z"


def test_get_feedback_empty_trait_summary_and_focus_points_still_returns_200(client, db_session):
    _login(client)
    _, session_id = _seed_completed_session(db_session, "fb-routes@example.com")

    ObservationRepository(db_session).create(session_id=session_id, entries=[])
    FeedbackRepository(db_session).create(session_id=session_id, trait_summary=[], focus_points=[])
    db_session.commit()

    r = client.get(f"/api/v1/sessions/{session_id}/feedback")
    assert r.status_code == 200
    assert r.json()["data"]["trait_summary"] == []
    assert r.json()["data"]["focus_points"] == []


# --- self-healing ---------------------------------------------------------


def test_get_feedback_self_heals_when_observation_exists_but_feedback_missing(client, app, db_session):
    """The core Feedback fix: Observation exists, session completed,
    but no Feedback row (its background task failed/never ran) — must
    run the Synthesizer inline rather than 404 forever."""
    _login(client)
    _, session_id = _seed_completed_session(db_session, "fb-routes@example.com")

    ObservationRepository(db_session).create(
        session_id=session_id,
        entries=[ObservationEntry(id=1, category="clarifies_ambiguity", fact="asked a question", turn_ref=[1])],
    )
    db_session.commit()

    fake_ai = _FakeFeedbackAIService(
        trait_summary=[TraitSummary(trait="clarifies_ambiguity", summary="did X", source_observations=[1])]
    )
    app.state.ai_service = fake_ai

    r = client.get(f"/api/v1/sessions/{session_id}/feedback")

    assert r.status_code == 200
    assert r.json()["data"]["session_id"] == session_id
    assert fake_ai.call_count == 1


def test_get_feedback_self_healing_persists_the_result(client, app, db_session):
    _login(client)
    _, session_id = _seed_completed_session(db_session, "fb-routes@example.com")

    ObservationRepository(db_session).create(session_id=session_id, entries=[])
    db_session.commit()

    fake_ai = _FakeFeedbackAIService()
    app.state.ai_service = fake_ai

    first = client.get(f"/api/v1/sessions/{session_id}/feedback")
    assert first.status_code == 200
    assert fake_ai.call_count == 1

    second = client.get(f"/api/v1/sessions/{session_id}/feedback")
    assert second.status_code == 200
    assert fake_ai.call_count == 1  # not re-invoked — found via find_by_session_id


def test_get_feedback_propagates_error_when_self_healing_retry_fails(client, app, db_session):
    _login(client)
    _, session_id = _seed_completed_session(db_session, "fb-routes@example.com")

    ObservationRepository(db_session).create(session_id=session_id, entries=[])
    db_session.commit()

    fake_ai = _FakeFeedbackAIService(raises=RuntimeError("LLM provider down"))
    app.state.ai_service = fake_ai

    r = client.get(f"/api/v1/sessions/{session_id}/feedback")
    assert r.status_code == 500


# --- history ---------------------------------------------------------------


def test_feedback_history_without_login_returns_401(client):
    r = client.get("/api/v1/feedback/history")
    assert r.status_code == 401


def test_feedback_history_returns_only_this_users_feedback(client, db_session):
    _login(client)
    _, session_id = _seed_completed_session(db_session, "fb-routes@example.com")
    ObservationRepository(db_session).create(session_id=session_id, entries=[])
    FeedbackRepository(db_session).create(session_id=session_id, trait_summary=[], focus_points=[])
    db_session.commit()

    r = client.get("/api/v1/feedback/history")
    assert r.status_code == 200
    body = r.json()["data"]
    assert len(body) == 1
    assert body[0]["session_id"] == session_id


def test_feedback_history_omits_sessions_without_feedback_yet(client, db_session):
    _login(client)
    _seed_in_progress_session(db_session, "fb-routes@example.com")

    r = client.get("/api/v1/feedback/history")
    assert r.status_code == 200
    assert r.json()["data"] == []
