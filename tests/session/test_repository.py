import pytest
from datetime import datetime, timezone

from auth.models import UserORM
from job_posting.models import JobPostingORM
from session.domain import SegmentChecklist
from session.errors import SegmentNotFoundError, SessionNotFoundError
from session.repository import SessionRepository


@pytest.fixture
def user_id(db_session) -> str:
    row = UserORM(email="sess-repo@example.com", name="Sess Repo", google_sub="sess-repo-sub")
    db_session.add(row)
    db_session.flush()
    return row.id


@pytest.fixture
def job_posting_id(db_session, user_id) -> str:
    row = JobPostingORM(user_id=user_id, title="Eng", description_raw="desc")
    db_session.add(row)
    db_session.flush()
    return row.id


def test_create_and_find_session(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    created = repo.create_session(
        user_id=user_id,
        job_posting_id=job_posting_id,
        duration_limit_minutes=30,
        strictness_mode="standard",
    )
    found = repo.find_session(user_id, created.id)
    assert found.id == created.id
    assert found.status == "in_progress"
    assert found.duration_limit_minutes == 30


def test_find_session_not_found_raises_sentinel(db_session, user_id):
    repo = SessionRepository(db_session)
    with pytest.raises(SessionNotFoundError):
        repo.find_session(user_id, "does-not-exist")


def test_find_session_enforces_tenant_isolation(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    created = repo.create_session(
        user_id=user_id,
        job_posting_id=job_posting_id,
        duration_limit_minutes=30,
        strictness_mode="standard",
    )
    with pytest.raises(SessionNotFoundError):
        repo.find_session("some-other-user", created.id)


def test_update_session_status_sets_ended_at(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    created = repo.create_session(
        user_id=user_id,
        job_posting_id=job_posting_id,
        duration_limit_minutes=30,
        strictness_mode="standard",
    )
    now = datetime.now(timezone.utc)
    updated = repo.update_session_status(user_id, created.id, "completed", ended_at=now)
    assert updated.status == "completed"
    assert updated.ended_at is not None


def test_list_sessions_orders_newest_first(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    first = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    second = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    results = repo.list_sessions(user_id)
    assert results[0].id == second.id
    assert results[1].id == first.id


# --- Segment -------------------------------------------------------------


def test_create_segment_starts_with_fresh_checklist(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    session = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    segment = repo.create_segment(
        session_id=session.id, segment_order=0, area="programming_algorithms",
        editor_available=True, duration_limit_minutes=10,
    )
    assert segment.checklist == SegmentChecklist()
    assert segment.status == "pending"
    assert segment.started_at is None


def test_update_segment_persists_checklist_and_status(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    session = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    segment = repo.create_segment(
        session_id=session.id, segment_order=0, area="programming_algorithms",
        editor_available=True, duration_limit_minutes=10,
    )
    new_checklist = SegmentChecklist(clarifies_ambiguity="demonstrated")
    started = datetime.now(timezone.utc)
    updated = repo.update_segment(segment.id, new_checklist, "in_progress", started_at=started)

    assert updated.checklist.clarifies_ambiguity == "demonstrated"
    assert updated.status == "in_progress"
    assert updated.started_at is not None

    reread = repo.find_segment(segment.id)
    assert reread.checklist.clarifies_ambiguity == "demonstrated"


def test_find_segment_not_found_raises_sentinel(db_session):
    repo = SessionRepository(db_session)
    with pytest.raises(SegmentNotFoundError):
        repo.find_segment("does-not-exist")


def test_list_segments_for_session_ordered_by_segment_order(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    session = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    repo.create_segment(session.id, 2, "system_design", False, 10)
    repo.create_segment(session.id, 0, "programming_algorithms", True, 10)
    repo.create_segment(session.id, 1, "frameworks_tools", False, 10)

    results = repo.list_segments_for_session(session.id)
    assert [s.segment_order for s in results] == [0, 1, 2]


# --- Turn ------------------------------------------------------------------


def test_create_turn_and_list_for_segment(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    session = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    segment = repo.create_segment(session.id, 0, "programming_algorithms", True, 10)

    repo.create_turn(segment.id, 1, "interviewer", "What would you clarify?")
    repo.create_turn(segment.id, 2, "candidate", "I'd ask about input size", code_snapshot=None)

    turns = repo.list_turns_for_segment(segment.id)
    assert len(turns) == 2
    assert turns[0].speaker == "interviewer"
    assert turns[1].speaker == "candidate"


def test_find_last_candidate_turn_returns_none_when_absent(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    session = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    segment = repo.create_segment(session.id, 0, "programming_algorithms", True, 10)
    repo.create_turn(segment.id, 1, "interviewer", "Opening question")

    assert repo.find_last_candidate_turn(segment.id) is None


def test_find_last_candidate_turn_returns_most_recent(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    session = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    segment = repo.create_segment(session.id, 0, "programming_algorithms", True, 10)
    repo.create_turn(segment.id, 1, "interviewer", "Q1")
    repo.create_turn(segment.id, 2, "candidate", "A1")
    repo.create_turn(segment.id, 3, "interviewer", "Q2")
    repo.create_turn(segment.id, 4, "candidate", "A2", code_snapshot="print('hi')")

    last = repo.find_last_candidate_turn(segment.id)
    assert last.content == "A2"
    assert last.code_snapshot == "print('hi')"


# --- timezone-awareness regression -------------------------------------
# SQLite drops tzinfo on DateTime columns regardless of timezone=True.
# Without normalization in the repository layer, comparing a DB-read
# datetime against datetime.now(timezone.utc) raises TypeError. See
# session/repository.py's _as_utc.


def test_session_started_at_is_timezone_aware_after_db_round_trip(db_session, user_id, job_posting_id):
    repo = SessionRepository(db_session)
    created = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    reread = repo.find_session(user_id, created.id)
    assert reread.started_at.tzinfo is not None

    # the actual failure mode this guards against: this must not raise
    from datetime import datetime, timezone
    elapsed = datetime.now(timezone.utc) - reread.started_at
    assert elapsed.total_seconds() >= 0


def test_segment_started_at_is_timezone_aware_after_db_round_trip(db_session, user_id, job_posting_id):
    from datetime import datetime, timezone

    repo = SessionRepository(db_session)
    session = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    segment = repo.create_segment(session.id, 0, "programming_algorithms", True, 10)
    updated = repo.update_segment(
        segment.id, segment.checklist, "in_progress", started_at=datetime.now(timezone.utc)
    )
    reread = repo.find_segment(updated.id)
    assert reread.started_at.tzinfo is not None

    elapsed = datetime.now(timezone.utc) - reread.started_at
    assert elapsed.total_seconds() >= 0


def test_turn_created_at_is_timezone_aware_after_db_round_trip(db_session, user_id, job_posting_id):
    from datetime import datetime, timezone

    repo = SessionRepository(db_session)
    session = repo.create_session(
        user_id=user_id, job_posting_id=job_posting_id,
        duration_limit_minutes=30, strictness_mode="standard",
    )
    segment = repo.create_segment(session.id, 0, "programming_algorithms", True, 10)
    repo.create_turn(segment.id, 1, "interviewer", "Q1")

    turns = repo.list_turns_for_segment(segment.id)
    assert turns[0].created_at.tzinfo is not None
    elapsed = datetime.now(timezone.utc) - turns[0].created_at
    assert elapsed.total_seconds() >= 0
