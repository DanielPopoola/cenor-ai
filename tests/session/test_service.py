from datetime import datetime, timedelta, timezone

import pytest

from candidate_profile.domain import CandidateProfile, CVStructured, Skill, WorkExperience
from job_posting.domain import JobPosting
from job_posting.errors import JobPostingNotFoundError
from session.domain import Segment, SegmentChecklist, Session, Turn
from session.errors import CandidateProfileIncompleteError, SessionNotInProgressError
from session.service import SessionService
from config import Settings


# --- Fakes -----------------------------------------------------------------


class FakeSessionRepository:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.segments: dict[str, Segment] = {}
        self.turns: dict[str, list[Turn]] = {}
        self._n = 1

    def create_session(self, user_id, job_posting_id, duration_limit_minutes, strictness_mode):
        s = Session(
            id=f"session-{self._n}", user_id=user_id, job_posting_id=job_posting_id,
            started_at=datetime.now(timezone.utc),
            duration_limit_minutes=duration_limit_minutes, strictness_mode=strictness_mode,
        )
        self._n += 1
        self.sessions[s.id] = s
        return s

    def find_session(self, user_id, session_id):
        from session.errors import SessionNotFoundError
        s = self.sessions.get(session_id)
        if s is None or s.user_id != user_id:
            raise SessionNotFoundError(session_id)
        return s

    def list_sessions(self, user_id):
        return [s for s in self.sessions.values() if s.user_id == user_id]

    def update_session_status(self, user_id, session_id, status, ended_at=None):
        s = self.find_session(user_id, session_id)
        updated = s.model_copy(update={"status": status, "ended_at": ended_at or s.ended_at})
        self.sessions[session_id] = updated
        return updated

    def create_segment(self, session_id, segment_order, area, editor_available, duration_limit_minutes):
        seg = Segment(
            id=f"segment-{self._n}", session_id=session_id, segment_order=segment_order,
            area=area, editor_available=editor_available,
            duration_limit_minutes=duration_limit_minutes,
        )
        self._n += 1
        self.segments[seg.id] = seg
        self.turns[seg.id] = []
        return seg

    def find_segment(self, segment_id):
        from session.errors import SegmentNotFoundError
        seg = self.segments.get(segment_id)
        if seg is None:
            raise SegmentNotFoundError(segment_id)
        return seg

    def list_segments_for_session(self, session_id):
        return sorted(
            (s for s in self.segments.values() if s.session_id == session_id),
            key=lambda s: s.segment_order,
        )

    def update_segment(self, segment_id, checklist, status, started_at=None):
        seg = self.find_segment(segment_id)
        updated = seg.model_copy(
            update={
                "checklist": checklist,
                "status": status,
                "started_at": started_at if started_at is not None else seg.started_at,
            }
        )
        self.segments[segment_id] = updated
        return updated

    def create_turn(self, segment_id, turn_number, speaker, content, code_snapshot=None):
        turn = Turn(
            id=f"turn-{self._n}", segment_id=segment_id, turn_number=turn_number,
            speaker=speaker, content=content, code_snapshot=code_snapshot,
            created_at=datetime.now(timezone.utc),
        )
        self._n += 1
        self.turns.setdefault(segment_id, []).append(turn)
        return turn

    def list_turns_for_segment(self, segment_id):
        return self.turns.get(segment_id, [])

    def find_last_candidate_turn(self, segment_id):
        candidate_turns = [t for t in self.turns.get(segment_id, []) if t.speaker == "candidate"]
        return candidate_turns[-1] if candidate_turns else None


class FakeCandidateProfileRepository:
    def __init__(self, profile: CandidateProfile | None = None):
        self._profile = profile

    def find_by_user_id_or_none(self, user_id):
        return self._profile


class FakeJobPostingRepository:
    def __init__(self, job: JobPosting | None = None):
        self._job = job

    def find_by_id(self, user_id, job_posting_id):
        if self._job is None:
            raise JobPostingNotFoundError(job_posting_id)
        return self._job


class FakeAIService:
    """Returns a queued sequence of InterviewerTurnResponses, one per
    call — lets tests script exactly how the "LLM" behaves turn by
    turn without hitting a real provider."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.call_count = 0
        self.received_calls: list[dict] = []

    async def run_interviewer_turn(self, **kwargs):
        self.call_count += 1
        self.received_calls.append(kwargs)
        return self._responses.pop(0)

    async def structure_cv(self, *a, **k):
        raise AssertionError("not exercised")

    async def structure_github(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_observer(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_feedback_synthesis(self, *a, **k):
        raise AssertionError("not exercised")


# --- Fixtures ----------------------------------------------------------


@pytest.fixture
def settings():
    return Settings(env="test")


def _complete_cv_profile(user_id="u1"):
    return CandidateProfile(
        id="p1", user_id=user_id,
        cv_attempted=True,
        cv_structured=CVStructured(
            is_valid=True,
            work_experience=[WorkExperience(company="Acme", title="Eng", start_date="2020")],
            skills=[Skill(name="Python")],
        ),
        updated_at=datetime.now(timezone.utc),
    )


def _job(user_id="u1"):
    return JobPosting(
        id="job-1", user_id=user_id, title="Eng", description_raw="desc",
        created_at=datetime.now(timezone.utc),
    )


def _in_progress_checklist_response(next_question="next?"):
    from session.domain import InterviewerTurnResponse
    return InterviewerTurnResponse(
        next_question=next_question,
        updated_checklist=SegmentChecklist(),
        segment_complete=False,
        reasoning="not enough evidence yet",
    )


def _fully_demonstrated_response():
    from session.domain import InterviewerTurnResponse
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


# --- create_session ------------------------------------------------------


async def test_create_session_blocked_when_no_profile(settings):
    repo = FakeSessionRepository()
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(None), FakeJobPostingRepository(_job()),
        FakeAIService([_in_progress_checklist_response()]),
    )
    with pytest.raises(CandidateProfileIncompleteError):
        await service.create_session("u1", "job-1")


async def test_create_session_blocked_when_cv_not_done(settings):
    repo = FakeSessionRepository()
    incomplete_profile = CandidateProfile(
        id="p1", user_id="u1", updated_at=datetime.now(timezone.utc)
    )
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(incomplete_profile),
        FakeJobPostingRepository(_job()), FakeAIService([_in_progress_checklist_response()]),
    )
    with pytest.raises(CandidateProfileIncompleteError):
        await service.create_session("u1", "job-1")


async def test_create_session_rejects_duration_outside_configured_range(settings):
    repo = FakeSessionRepository()
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), FakeAIService([_in_progress_checklist_response()]),
    )
    from common.errors import ValidationError

    with pytest.raises(ValidationError):
        await service.create_session("u1", "job-1", duration_limit_minutes=999)


async def test_create_session_success_creates_4_segments_and_starts_first(settings):
    repo = FakeSessionRepository()
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), FakeAIService([_in_progress_checklist_response("first q")]),
    )
    session, first_segment, result = await service.create_session("u1", "job-1", 30)

    assert session.status == "in_progress"
    all_segments = repo.list_segments_for_session(session.id)
    assert len(all_segments) == 4
    assert {s.area for s in all_segments} == {
        "programming_algorithms", "frameworks_tools", "specialized", "system_design",
    }
    assert first_segment.status == "in_progress"
    assert first_segment.started_at is not None
    assert result.outcome == "continue"
    assert result.next_question == "first q"


# --- submit_turn: checklist-driven completion ---------------------------


async def test_submit_turn_persists_candidate_turn_and_returns_next_question(settings):
    repo = FakeSessionRepository()
    ai = FakeAIService([_in_progress_checklist_response("opening"), _in_progress_checklist_response("follow-up")])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, segment, _ = await service.create_session("u1", "job-1", 30)

    result = await service.submit_turn("u1", session.id, "I would clarify the input constraints first")
    assert result.outcome == "continue"
    assert result.next_question == "follow-up"
    turns = repo.list_turns_for_segment(segment.id)
    assert any(t.speaker == "candidate" and "clarify" in t.content for t in turns)


async def test_submit_turn_stops_at_segment_boundary_without_auto_chaining(settings):
    """The core fix: completing a segment must NOT trigger a second
    LLM call in the same submit_turn — it stops and returns
    'segment_transitioned', leaving the next question for a separate
    start_next_question() call. Bounds per-request latency to one
    Interviewer call."""
    repo = FakeSessionRepository()
    ai = FakeAIService([
        _in_progress_checklist_response("opening segment 0"),
        _fully_demonstrated_response(),  # completes segment 0
    ])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, first_segment, _ = await service.create_session("u1", "job-1", 30)

    calls_before = ai.call_count
    result = await service.submit_turn("u1", session.id, "an answer")

    assert ai.call_count == calls_before + 1  # exactly one LLM call, no chaining
    assert result.outcome == "segment_transitioned"
    assert result.next_question is None


async def test_submit_turn_advances_to_next_segment_when_checklist_complete(settings):
    repo = FakeSessionRepository()
    ai = FakeAIService([
        _in_progress_checklist_response("opening segment 0"),
        _fully_demonstrated_response(),  # completes segment 0
    ])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, first_segment, _ = await service.create_session("u1", "job-1", 30)

    result = await service.submit_turn("u1", session.id, "an answer")

    all_segments = repo.list_segments_for_session(session.id)
    completed = [s for s in all_segments if s.status == "completed"]
    in_progress = [s for s in all_segments if s.status == "in_progress"]
    assert len(completed) == 1
    assert completed[0].id == first_segment.id
    assert len(in_progress) == 1
    assert in_progress[0].segment_order == 1
    assert result.outcome == "segment_transitioned"


async def test_start_next_question_returns_new_segments_opener(settings):
    repo = FakeSessionRepository()
    ai = FakeAIService([
        _in_progress_checklist_response("opening segment 0"),
        _fully_demonstrated_response(),
        _in_progress_checklist_response("opening segment 1"),
    ])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, _, _ = await service.create_session("u1", "job-1", 30)
    transition = await service.submit_turn("u1", session.id, "an answer")
    assert transition.outcome == "segment_transitioned"

    opener = await service.start_next_question("u1", session.id)
    assert opener.outcome == "continue"
    assert opener.next_question == "opening segment 1"


async def test_submit_turn_completes_session_after_last_segment(settings):
    """4 segments total — completing all 4 in sequence ends the whole
    Session, matching the one-sitting model (Section 2a). Each segment
    transition requires its own start_next_question() call, per the
    no-auto-chain fix."""
    repo = FakeSessionRepository()
    responses = [_in_progress_checklist_response("open 0")]
    for i in range(4):
        responses.append(_fully_demonstrated_response())  # complete segment i
        if i < 3:
            responses.append(_in_progress_checklist_response(f"open {i + 1}"))
    ai = FakeAIService(responses)
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, _, _ = await service.create_session("u1", "job-1", 30)

    result = await service.submit_turn("u1", session.id, "answer 0")
    for _ in range(3):
        assert result.outcome == "segment_transitioned"
        opener = await service.start_next_question("u1", session.id)
        assert opener.outcome == "continue"
        result = await service.submit_turn("u1", session.id, "next answer")

    assert result.outcome == "session_completed"
    assert result.session.status == "completed"
    assert result.session.ended_at is not None
    assert result.next_question is None


# --- submit_turn: time-driven completion (deterministic override) -------


async def test_segment_time_expiry_forces_completion_even_if_llm_says_not_complete(settings):
    """The core deterministic-override rule: even when the LLM returns
    segment_complete=False, an expired segment timer must still force
    completion — never left to the model's judgment."""
    repo = FakeSessionRepository()
    ai = FakeAIService([
        _in_progress_checklist_response("opening"),
        _in_progress_checklist_response("still not complete per LLM"),
    ])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, first_segment, _ = await service.create_session("u1", "job-1", 30)

    # Force the segment to look like its time already expired.
    expired_start = datetime.now(timezone.utc) - timedelta(minutes=999)
    repo.segments[first_segment.id] = repo.segments[first_segment.id].model_copy(
        update={"started_at": expired_start}
    )

    result = await service.submit_turn("u1", session.id, "an answer")

    all_segments = repo.list_segments_for_session(session.id)
    assert all_segments[0].status == "completed"  # forced despite LLM saying not complete
    assert result.outcome == "segment_transitioned"


async def test_submit_turn_raises_when_session_not_in_progress(settings):
    repo = FakeSessionRepository()
    ai = FakeAIService([_in_progress_checklist_response()])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, _, _ = await service.create_session("u1", "job-1", 30)
    repo.update_session_status("u1", session.id, "completed", ended_at=datetime.now(timezone.utc))

    with pytest.raises(SessionNotInProgressError):
        await service.submit_turn("u1", session.id, "too late")


# --- lazy abandonment --------------------------------------------------


async def test_get_session_marks_abandoned_when_deadline_passed(settings):
    repo = FakeSessionRepository()
    ai = FakeAIService([_in_progress_checklist_response()])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, _, _ = await service.create_session("u1", "job-1", 30)

    # backdate started_at so the deadline has already passed
    repo.sessions[session.id] = repo.sessions[session.id].model_copy(
        update={"started_at": datetime.now(timezone.utc) - timedelta(minutes=999)}
    )

    result = service.get_session("u1", session.id)
    assert result.status == "abandoned"
    assert result.ended_at is not None


async def test_get_session_leaves_in_progress_session_untouched_before_deadline(settings):
    repo = FakeSessionRepository()
    ai = FakeAIService([_in_progress_checklist_response()])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(_job()), ai,
    )
    session, _, _ = await service.create_session("u1", "job-1", 30)

    result = service.get_session("u1", session.id)
    assert result.status == "in_progress"


# --- candidate/job context wiring ----------------------------------------


async def test_interviewer_receives_real_cv_context_not_empty_dict(settings):
    repo = FakeSessionRepository()
    profile = _complete_cv_profile()
    ai = FakeAIService([_in_progress_checklist_response()])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(profile),
        FakeJobPostingRepository(_job()), ai,
    )
    await service.create_session("u1", "job-1", 30)

    call = ai.received_calls[0]
    assert call["candidate_context"]["cv"]["skills"][0]["name"] == "Python"
    assert call["candidate_context"]["cv"]["work_experience"][0]["company"] == "Acme"


async def test_interviewer_receives_real_job_context_not_empty_dict(settings):
    repo = FakeSessionRepository()
    job = _job()
    ai = FakeAIService([_in_progress_checklist_response()])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(_complete_cv_profile()),
        FakeJobPostingRepository(job), ai,
    )
    await service.create_session("u1", "job-1", 30)

    call = ai.received_calls[0]
    assert call["job_context"]["title"] == "Eng"
    assert call["job_context"]["description"] == "desc"


async def test_candidate_context_omits_github_when_not_connected(settings):
    repo = FakeSessionRepository()
    profile = _complete_cv_profile()  # github_structured is None
    ai = FakeAIService([_in_progress_checklist_response()])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(profile),
        FakeJobPostingRepository(_job()), ai,
    )
    await service.create_session("u1", "job-1", 30)

    call = ai.received_calls[0]
    assert "github" not in call["candidate_context"]


async def test_candidate_context_includes_github_when_connected(settings):
    from candidate_profile.domain import GitHubStructured

    repo = FakeSessionRepository()
    profile = _complete_cv_profile().model_copy(
        update={"github_structured": GitHubStructured(is_valid=True, bio="Builder")}
    )
    ai = FakeAIService([_in_progress_checklist_response()])
    service = SessionService(
        settings, repo, FakeCandidateProfileRepository(profile),
        FakeJobPostingRepository(_job()), ai,
    )
    await service.create_session("u1", "job-1", 30)

    call = ai.received_calls[0]
    assert call["candidate_context"]["github"]["bio"] == "Builder"
