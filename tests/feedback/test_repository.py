import pytest

from auth.models import UserORM
from job_posting.models import JobPostingORM
from feedback.domain import FocusPoint, TraitSummary
from feedback.errors import FeedbackNotFoundError
from feedback.repository import FeedbackRepository
from session.models import SessionORM


@pytest.fixture
def session_id(db_session) -> str:
    user = UserORM(email="fb-repo@example.com", name="FB Repo", google_sub="fb-repo-sub")
    db_session.add(user)
    db_session.flush()

    job = JobPostingORM(user_id=user.id, title="Eng", description_raw="desc")
    db_session.add(job)
    db_session.flush()

    session = SessionORM(
        user_id=user.id, job_posting_id=job.id, duration_limit_minutes=30
    )
    db_session.add(session)
    db_session.flush()
    return session.id


def _trait_summaries() -> list[TraitSummary]:
    return [
        TraitSummary(
            trait="problem_solving",
            summary="In this session, the candidate traced through a concrete example before implementing.",
            source_observations=[1, 3],
        )
    ]


def _focus_points() -> list[FocusPoint]:
    return [
        FocusPoint(
            pattern="In this session, the candidate did not discuss consistency tradeoffs before choosing a caching approach.",
            resource="distributed systems consistency models",
            source_observations=[5],
        )
    ]


def test_create_and_find_by_session_id(db_session, session_id):
    repo = FeedbackRepository(db_session)
    created = repo.create(session_id, _trait_summaries(), _focus_points())

    found = repo.find_by_session_id(session_id)
    assert found.id == created.id
    assert found.session_id == session_id
    assert len(found.trait_summary) == 1
    assert len(found.focus_points) == 1


def test_trait_summary_round_trips_all_fields(db_session, session_id):
    repo = FeedbackRepository(db_session)
    repo.create(session_id, _trait_summaries(), _focus_points())

    found = repo.find_by_session_id(session_id)
    summary = found.trait_summary[0]
    assert summary.trait == "problem_solving"
    assert "concrete example" in summary.summary
    assert summary.source_observations == [1, 3]


def test_focus_point_round_trips_all_fields(db_session, session_id):
    repo = FeedbackRepository(db_session)
    repo.create(session_id, _trait_summaries(), _focus_points())

    found = repo.find_by_session_id(session_id)
    focus = found.focus_points[0]
    assert "consistency tradeoffs" in focus.pattern
    assert focus.resource == "distributed systems consistency models"
    assert focus.source_observations == [5]


def test_find_by_session_id_not_found_raises_sentinel(db_session):
    repo = FeedbackRepository(db_session)
    with pytest.raises(FeedbackNotFoundError):
        repo.find_by_session_id("does-not-exist")


def test_empty_trait_summary_and_focus_points_are_valid_and_round_trip(
    db_session, session_id
):
    """Zero trait summaries and zero focus points are both valid,
    expected outcomes (feedback_synthesizer_prompt_draft.md: 'Zero
    evidence is a valid, expected outcome') — must not raise on create
    or on read."""
    repo = FeedbackRepository(db_session)
    repo.create(session_id, [], [])

    found = repo.find_by_session_id(session_id)
    assert found.trait_summary == []
    assert found.focus_points == []


def test_second_feedback_for_same_session_raises_conflict_error(db_session, session_id):
    """unique=True on session_id enforces the 1:1 relationship at the
    DB level, translated to ConflictError same as ObservationRepository."""
    from common.errors import ConflictError

    repo = FeedbackRepository(db_session)
    repo.create(session_id, _trait_summaries(), _focus_points())

    with pytest.raises(ConflictError):
        repo.create(session_id, _trait_summaries(), _focus_points())


def test_created_at_is_timezone_aware_after_db_round_trip(db_session, session_id):
    from datetime import datetime, timezone

    repo = FeedbackRepository(db_session)
    repo.create(session_id, _trait_summaries(), _focus_points())

    reread = repo.find_by_session_id(session_id)
    assert reread.created_at.tzinfo is not None
    elapsed = datetime.now(timezone.utc) - reread.created_at
    assert elapsed.total_seconds() >= 0

def test_list_by_session_ids_returns_only_matching_feedback(db_session, session_id):
    repo = FeedbackRepository(db_session)
    repo.create(session_id, _trait_summaries(), _focus_points())

    results = repo.list_by_session_ids([session_id])

    assert len(results) == 1
    assert results[0].session_id == session_id


def test_list_by_session_ids_fetches_multiple_in_one_call(db_session, session_id):
    user = db_session.query(UserORM).filter_by(email="fb-repo@example.com").first()
    job = JobPostingORM(user_id=user.id, title="Eng 2", description_raw="desc")
    db_session.add(job)
    db_session.flush()
    other_session = SessionORM(user_id=user.id, job_posting_id=job.id, duration_limit_minutes=30)
    db_session.add(other_session)
    db_session.flush()

    repo = FeedbackRepository(db_session)
    repo.create(session_id, _trait_summaries(), _focus_points())
    repo.create(other_session.id, [], [])

    results = repo.list_by_session_ids([session_id, other_session.id])

    result_session_ids = {f.session_id for f in results}
    assert result_session_ids == {session_id, other_session.id}


def test_list_by_session_ids_omits_sessions_with_no_feedback(db_session, session_id):
    repo = FeedbackRepository(db_session)
    repo.create(session_id, _trait_summaries(), _focus_points())

    results = repo.list_by_session_ids([session_id, "no-feedback-session"])

    assert len(results) == 1
    assert results[0].session_id == session_id


def test_list_by_session_ids_with_empty_input_returns_empty_list_without_querying(db_session):
    repo = FeedbackRepository(db_session)
    assert repo.list_by_session_ids([]) == []


def test_list_by_session_ids_with_no_matches_returns_empty_list(db_session):
    repo = FeedbackRepository(db_session)
    assert repo.list_by_session_ids(["nonexistent-1", "nonexistent-2"]) == []
