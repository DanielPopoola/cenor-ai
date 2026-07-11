import pytest

from auth.models import UserORM
from job_posting.errors import JobPostingNotFoundError
from job_posting.repository import JobPostingRepository


@pytest.fixture
def user_id(db_session) -> str:
    row = UserORM(email="jp-repo@example.com", name="JP Repo", google_sub="jp-repo-sub")
    db_session.add(row)
    db_session.flush()
    return row.id


@pytest.fixture
def other_user_id(db_session) -> str:
    row = UserORM(email="jp-other@example.com", name="Other", google_sub="jp-other-sub")
    db_session.add(row)
    db_session.flush()
    return row.id


def test_create_and_find_by_id(db_session, user_id):
    repo = JobPostingRepository(db_session)
    created = repo.create(
        user_id=user_id,
        title="Backend Engineer",
        description_raw="Build things",
        company="Acme",
        url="https://acme.example/jobs/1",
    )

    found = repo.find_by_id(user_id, created.id)
    assert found.title == "Backend Engineer"
    assert found.company == "Acme"
    assert found.url == "https://acme.example/jobs/1"


def test_create_without_company_or_url_is_allowed(db_session, user_id):
    repo = JobPostingRepository(db_session)
    created = repo.create(user_id=user_id, title="Eng", description_raw="desc")
    assert created.company is None
    assert created.url is None


def test_find_by_id_not_found_raises_sentinel(db_session, user_id):
    repo = JobPostingRepository(db_session)
    with pytest.raises(JobPostingNotFoundError):
        repo.find_by_id(user_id, "does-not-exist")


def test_find_by_id_enforces_tenant_isolation(db_session, user_id, other_user_id):
    """A job posting belonging to another user must be invisible, not
    just filtered from lists — direct ID lookup must also fail."""
    repo = JobPostingRepository(db_session)
    created = repo.create(user_id=user_id, title="Eng", description_raw="desc")

    with pytest.raises(JobPostingNotFoundError):
        repo.find_by_id(other_user_id, created.id)


def test_list_for_user_returns_only_that_users_postings(db_session, user_id, other_user_id):
    repo = JobPostingRepository(db_session)
    repo.create(user_id=user_id, title="Mine 1", description_raw="d")
    repo.create(user_id=user_id, title="Mine 2", description_raw="d")
    repo.create(user_id=other_user_id, title="Not mine", description_raw="d")

    results = repo.list_for_user(user_id)
    assert len(results) == 2
    assert {r.title for r in results} == {"Mine 1", "Mine 2"}


def test_list_for_user_returns_empty_list_when_none_exist(db_session, user_id):
    """Expected-empty: no postings yet is a valid state, not an error."""
    repo = JobPostingRepository(db_session)
    assert repo.list_for_user(user_id) == []


def test_list_for_user_orders_newest_first(db_session, user_id):
    repo = JobPostingRepository(db_session)
    first = repo.create(user_id=user_id, title="First", description_raw="d")
    second = repo.create(user_id=user_id, title="Second", description_raw="d")

    results = repo.list_for_user(user_id)
    assert results[0].id == second.id
    assert results[1].id == first.id


def test_same_job_posting_can_exist_multiple_times_per_user(db_session, user_id):
    """Unlike CandidateProfile, JobPosting is many-per-user — a
    candidate may retry the same posting across sessions (TDD)."""
    repo = JobPostingRepository(db_session)
    repo.create(user_id=user_id, title="Same Title", description_raw="d1")
    repo.create(user_id=user_id, title="Same Title", description_raw="d2")

    results = repo.list_for_user(user_id)
    assert len(results) == 2
