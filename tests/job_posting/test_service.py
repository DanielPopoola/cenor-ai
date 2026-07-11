from datetime import datetime, timezone

import pytest

from job_posting.domain import JobPosting
from job_posting.errors import JobPostingNotFoundError
from job_posting.service import JobPostingService


class FakeJobPostingRepository:
    def __init__(self):
        self._by_id: dict[str, JobPosting] = {}
        self._next_id = 1

    def create(self, user_id, title, description_raw, company=None, url=None):
        job = JobPosting(
            id=f"job-{self._next_id}",
            user_id=user_id,
            title=title,
            company=company,
            url=url,
            description_raw=description_raw,
            created_at=datetime.now(timezone.utc),
        )
        self._next_id += 1
        self._by_id[job.id] = job
        return job

    def find_by_id(self, user_id, job_posting_id):
        job = self._by_id.get(job_posting_id)
        if job is None or job.user_id != user_id:
            raise JobPostingNotFoundError(job_posting_id)
        return job

    def list_for_user(self, user_id):
        return [j for j in self._by_id.values() if j.user_id == user_id]


@pytest.fixture
def fake_repo() -> FakeJobPostingRepository:
    return FakeJobPostingRepository()


@pytest.fixture
def service(fake_repo) -> JobPostingService:
    return JobPostingService(fake_repo)


def test_create_delegates_to_repository(service):
    job = service.create(user_id="u1", title="Eng", description_raw="desc", company="Acme")
    assert job.title == "Eng"
    assert job.company == "Acme"


def test_get_returns_owned_posting(service):
    created = service.create(user_id="u1", title="Eng", description_raw="desc")
    found = service.get("u1", created.id)
    assert found.id == created.id


def test_get_raises_for_other_users_posting(service):
    created = service.create(user_id="u1", title="Eng", description_raw="desc")
    with pytest.raises(JobPostingNotFoundError):
        service.get("u2", created.id)


def test_list_for_user_returns_only_owned_postings(service):
    service.create(user_id="u1", title="A", description_raw="d")
    service.create(user_id="u2", title="B", description_raw="d")
    results = service.list_for_user("u1")
    assert len(results) == 1
    assert results[0].title == "A"
