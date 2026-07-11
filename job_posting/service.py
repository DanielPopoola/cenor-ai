from job_posting.domain import JobPosting
from job_posting.repository import JobPostingRepository


class JobPostingService:
    def __init__(self, repository: JobPostingRepository):
        self._repository = repository

    def create(
        self,
        user_id: str,
        title: str,
        description_raw: str,
        company: str | None = None,
        url: str | None = None,
    ) -> JobPosting:
        return self._repository.create(
            user_id=user_id,
            title=title,
            description_raw=description_raw,
            company=company,
            url=url,
        )

    def get(self, user_id: str, job_posting_id: str) -> JobPosting:
        return self._repository.find_by_id(user_id, job_posting_id)

    def list_for_user(self, user_id: str) -> list[JobPosting]:
        return self._repository.list_for_user(user_id)
