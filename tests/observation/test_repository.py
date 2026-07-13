import pytest

from auth.models import UserORM
from job_posting.models import JobPostingORM
from observation.domain import ObservationEntry
from observation.errors import ObservationNotFoundError
from observation.repository import ObservationRepository
from session.models import SessionORM


@pytest.fixture
def session_id(db_session) -> str:
    user = UserORM(email="obs-repo@example.com", name="Obs Repo", google_sub="obs-repo-sub")
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


def _entries() -> list[ObservationEntry]:
    return [
        ObservationEntry(
            id=1,
            category="clarifies_ambiguity",
            fact="In turn 2, the candidate asked about input size constraints.",
            turn_ref=[2],
        ),
        ObservationEntry(
            id=2,
            category="code_matches_plan",
            fact="The code in turn 9 follows the early-return approach stated in turn 4.",
            turn_ref=[4, 9],
        ),
    ]


def test_create_and_find_by_session_id(db_session, session_id):
    repo = ObservationRepository(db_session)
    created = repo.create(session_id, _entries())

    found = repo.find_by_session_id(session_id)
    assert found.id == created.id
    assert found.session_id == session_id
    assert len(found.entries) == 2


def test_entries_round_trip_all_fields(db_session, session_id):
    repo = ObservationRepository(db_session)
    repo.create(session_id, _entries())

    found = repo.find_by_session_id(session_id)
    first = found.entries[0]
    assert first.id == 1
    assert first.category == "clarifies_ambiguity"
    assert "input size" in first.fact
    assert first.turn_ref == [2]


def test_multi_turn_ref_round_trips(db_session, session_id):
    """code_matches_plan entries cite 2+ turns — must not be truncated
    or collapsed on round trip."""
    repo = ObservationRepository(db_session)
    repo.create(session_id, _entries())

    found = repo.find_by_session_id(session_id)
    code_entry = next(e for e in found.entries if e.category == "code_matches_plan")
    assert code_entry.turn_ref == [4, 9]


def test_find_by_session_id_not_found_raises_sentinel(db_session):
    repo = ObservationRepository(db_session)
    with pytest.raises(ObservationNotFoundError):
        repo.find_by_session_id("does-not-exist")


def test_empty_entries_list_is_valid_and_round_trips(db_session, session_id):
    """Zero observations for a session is a valid, expected outcome
    (observer_prompt_draft.md) — not an error state, must not raise
    on create or on read."""
    repo = ObservationRepository(db_session)
    repo.create(session_id, [])

    found = repo.find_by_session_id(session_id)
    assert found.entries == []


def test_second_observation_for_same_session_violates_unique_constraint(
    db_session, session_id
):
    """unique=True on session_id enforces the 1:1 relationship at the
    DB level — mirrors CandidateProfileORM.user_id's constraint."""
    from sqlalchemy.exc import IntegrityError

    repo = ObservationRepository(db_session)
    repo.create(session_id, _entries())

    with pytest.raises(IntegrityError):
        repo.create(session_id, _entries())


def test_created_at_is_timezone_aware_after_db_round_trip(db_session, session_id):
    from datetime import datetime, timezone

    repo = ObservationRepository(db_session)
    repo.create(session_id, _entries())

    reread = repo.find_by_session_id(session_id)
    assert reread.created_at.tzinfo is not None
    elapsed = datetime.now(timezone.utc) - reread.created_at
    assert elapsed.total_seconds() >= 0
