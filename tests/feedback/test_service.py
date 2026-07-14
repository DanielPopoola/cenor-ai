from datetime import datetime, timezone

import pytest

from candidate_profile.domain import CandidateProfile, CVStructured, Skill
from feedback.domain import Feedback, FeedbackResult, TraitSummary
from feedback.service import FeedbackService
from observation.domain import Observation, ObservationEntry
from session.domain import Segment, Session
from session.errors import SessionNotFoundError


class FakeSessionRepository:
    def __init__(self, session: Session, segments: list[Segment]):
        self._session = session
        self._segments = segments

    def find_session(self, user_id, session_id):
        if self._session.user_id != user_id or self._session.id != session_id:
            raise SessionNotFoundError(session_id)
        return self._session

    def list_segments_for_session(self, session_id):
        return self._segments


class FakeObservationRepository:
    def __init__(self, observation: Observation):
        self._observation = observation

    def find_by_session_id(self, session_id):
        return self._observation


class FakeFeedbackRepository:
    def __init__(self):
        self.created_with: dict | None = None
        self._next_id = 1

    def create(self, session_id, trait_summary, focus_points):
        self.created_with = {
            "session_id": session_id,
            "trait_summary": trait_summary,
            "focus_points": focus_points,
        }
        feedback = Feedback(
            id=f"fb-{self._next_id}", session_id=session_id,
            trait_summary=trait_summary, focus_points=focus_points,
            created_at=datetime.now(timezone.utc),
        )
        self._next_id += 1
        return feedback

    def find_by_session_id(self, session_id):
        raise AssertionError("not exercised in these tests")


class FakeCandidateProfileRepository:
    def __init__(self, profile: CandidateProfile | None):
        self._profile = profile

    def find_by_user_id_or_none(self, user_id):
        return self._profile


class FakeAIService:
    def __init__(self, result: FeedbackResult | None = None):
        self._result = result or FeedbackResult(trait_summary=[], focus_points=[])
        self.received_observations = None
        self.received_lens_type = None
        self.received_trait_mapping = None
        self.received_candidate_profile_summary = None

    async def run_feedback_synthesis(
        self, observations, lens_type, trait_mapping, candidate_profile_summary
    ):
        self.received_observations = observations
        self.received_lens_type = lens_type
        self.received_trait_mapping = trait_mapping
        self.received_candidate_profile_summary = candidate_profile_summary
        return self._result

    async def structure_cv(self, *a, **k):
        raise AssertionError("not exercised")

    async def structure_github(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_interviewer_turn(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_observer(self, *a, **k):
        raise AssertionError("not exercised")


def _session(user_id="u1", session_id="s1") -> Session:
    return Session(
        id=session_id, user_id=user_id, job_posting_id="job-1",
        started_at=datetime.now(timezone.utc), duration_limit_minutes=30,
    )


def _segment(area: str, editor_available: bool) -> Segment:
    return Segment(
        id=f"segment-{area}", session_id="s1", segment_order=0,
        area=area, editor_available=editor_available, duration_limit_minutes=10,
    )


def _observation(session_id="s1") -> Observation:
    return Observation(
        id="obs-1", session_id=session_id,
        entries=[
            ObservationEntry(
                id=1, category="clarifies_ambiguity",
                fact="The candidate asked a clarifying question.", turn_ref=[1],
            )
        ],
        created_at=datetime.now(timezone.utc),
    )


def _profile(user_id="u1") -> CandidateProfile:
    return CandidateProfile(
        id="p1", user_id=user_id,
        cv_structured=CVStructured(is_valid=True, skills=[Skill(name="Python")]),
        updated_at=datetime.now(timezone.utc),
    )


def _service(session_repo, observation_repo, feedback_repo, profile_repo, ai):
    return FeedbackService(
        session_repository=session_repo,
        observation_repository=observation_repo,
        feedback_repository=feedback_repo,
        candidate_profile_repository=profile_repo,
        ai_service=ai,
    )


async def test_run_feedback_synthesis_persists_synthesizer_output():
    session_repo = FakeSessionRepository(_session(), [_segment("programming_algorithms", True)])
    feedback_repo = FakeFeedbackRepository()
    result = FeedbackResult(
        trait_summary=[
            TraitSummary(trait="problem_solving", summary="did X", source_observations=[1])
        ],
        focus_points=[],
    )
    ai = FakeAIService(result=result)

    service = _service(session_repo, FakeObservationRepository(_observation()), feedback_repo, FakeCandidateProfileRepository(_profile()), ai)
    feedback = await service.run_feedback_synthesis("u1", "s1")

    assert feedback.session_id == "s1"
    assert len(feedback.trait_summary) == 1
    assert feedback_repo.created_with["session_id"] == "s1"


async def test_run_feedback_synthesis_enforces_tenant_isolation():
    session_repo = FakeSessionRepository(_session(user_id="owner"), [_segment("system_design", False)])
    service = _service(
        session_repo, FakeObservationRepository(_observation()), FakeFeedbackRepository(),
        FakeCandidateProfileRepository(_profile()), FakeAIService(),
    )

    with pytest.raises(SessionNotFoundError):
        await service.run_feedback_synthesis("not-the-owner", "s1")


async def test_run_feedback_synthesis_passes_observation_entries_to_ai():
    session_repo = FakeSessionRepository(_session(), [_segment("system_design", False)])
    observation = _observation()
    ai = FakeAIService()

    service = _service(session_repo, FakeObservationRepository(observation), FakeFeedbackRepository(), FakeCandidateProfileRepository(_profile()), ai)
    await service.run_feedback_synthesis("u1", "s1")

    assert ai.received_observations == observation.entries


async def test_run_feedback_synthesis_derives_coding_lens_and_trait_mapping():
    session_repo = FakeSessionRepository(_session(), [_segment("programming_algorithms", True)])
    ai = FakeAIService()

    service = _service(session_repo, FakeObservationRepository(_observation()), FakeFeedbackRepository(), FakeCandidateProfileRepository(_profile()), ai)
    await service.run_feedback_synthesis("u1", "s1")

    assert ai.received_lens_type == "coding"
    assert "execution_integrity" in ai.received_trait_mapping


async def test_run_feedback_synthesis_derives_conversational_lens_and_trait_mapping():
    session_repo = FakeSessionRepository(_session(), [_segment("system_design", False)])
    ai = FakeAIService()

    service = _service(session_repo, FakeObservationRepository(_observation()), FakeFeedbackRepository(), FakeCandidateProfileRepository(_profile()), ai)
    await service.run_feedback_synthesis("u1", "s1")

    assert ai.received_lens_type == "conversational"
    assert "execution_integrity" not in ai.received_trait_mapping


async def test_run_feedback_synthesis_passes_candidate_profile_summary():
    session_repo = FakeSessionRepository(_session(), [_segment("system_design", False)])
    ai = FakeAIService()
    profile = _profile()

    service = _service(session_repo, FakeObservationRepository(_observation()), FakeFeedbackRepository(), FakeCandidateProfileRepository(profile), ai)
    await service.run_feedback_synthesis("u1", "s1")

    assert "Python" in ai.received_candidate_profile_summary


async def test_run_feedback_synthesis_handles_missing_profile_gracefully():
    """A missing CandidateProfile must not block feedback generation —
    resource relevance context degrades to an empty string rather than
    raising."""
    session_repo = FakeSessionRepository(_session(), [_segment("system_design", False)])
    ai = FakeAIService()

    service = _service(session_repo, FakeObservationRepository(_observation()), FakeFeedbackRepository(), FakeCandidateProfileRepository(None), ai)
    await service.run_feedback_synthesis("u1", "s1")

    assert ai.received_candidate_profile_summary == ""


async def test_run_feedback_synthesis_with_zero_traits_and_focus_points_is_valid():
    """Zero trait summaries and zero focus points are valid, expected
    Synthesizer outcomes — must not raise."""
    session_repo = FakeSessionRepository(_session(), [_segment("system_design", False)])
    ai = FakeAIService(result=FeedbackResult(trait_summary=[], focus_points=[]))

    service = _service(session_repo, FakeObservationRepository(_observation()), FakeFeedbackRepository(), FakeCandidateProfileRepository(_profile()), ai)
    feedback = await service.run_feedback_synthesis("u1", "s1")

    assert feedback.trait_summary == []
    assert feedback.focus_points == []


async def test_run_feedback_synthesis_raises_when_ai_service_unavailable():
    from common.errors import ValidationError

    session_repo = FakeSessionRepository(_session(), [_segment("system_design", False)])
    service = _service(session_repo, FakeObservationRepository(_observation()), FakeFeedbackRepository(), FakeCandidateProfileRepository(_profile()), ai=None)

    with pytest.raises(ValidationError):
        await service.run_feedback_synthesis("u1", "s1")


async def test_run_feedback_synthesis_raises_when_observation_missing():
    """Feedback cannot run without Observer output — this must
    propagate ObservationNotFoundError, not silently substitute
    something else."""
    from observation.errors import ObservationNotFoundError

    class _MissingObservationRepository:
        def find_by_session_id(self, session_id):
            raise ObservationNotFoundError(session_id)

    session_repo = FakeSessionRepository(_session(), [_segment("system_design", False)])
    service = _service(session_repo, _MissingObservationRepository(), FakeFeedbackRepository(), FakeCandidateProfileRepository(_profile()), FakeAIService())

    with pytest.raises(ObservationNotFoundError):
        await service.run_feedback_synthesis("u1", "s1")
