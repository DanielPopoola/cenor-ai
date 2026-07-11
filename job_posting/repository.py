from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from job_posting.domain import JobPosting
from job_posting.errors import JobPostingNotFoundError
from job_posting.models import JobPostingORM


def _to_domain(row: JobPostingORM) -> JobPosting:
    return JobPosting(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        company=row.company,
        url=row.url,
        description_raw=row.description_raw,
        created_at=row.created_at,
    )


class JobPostingRepository:
    def __init__(self, db: DBSession):
        self._db = db

    def create(
        self,
        user_id: str,
        title: str,
        description_raw: str,
        company: str | None = None,
        url: str | None = None,
    ) -> JobPosting:
        row = JobPostingORM(
            user_id=user_id,
            title=title,
            company=company,
            url=url,
            description_raw=description_raw,
        )
        self._db.add(row)
        self._db.flush()
        return _to_domain(row)

    def find_by_id(self, user_id: str, job_posting_id: str) -> JobPosting:
        # Hard, non-optional user_id filter baked into the query itself
        # — a caller cannot omit tenant isolation, per Security section.
        row = self._db.execute(
            select(JobPostingORM).where(
                JobPostingORM.id == job_posting_id, JobPostingORM.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is None:
            raise JobPostingNotFoundError(
                f"No job posting id={job_posting_id} for user_id={user_id}"
            )
        return _to_domain(row)

    def list_for_user(self, user_id: str) -> list[JobPosting]:
        rows = (
            self._db.execute(
                select(JobPostingORM)
                .where(JobPostingORM.user_id == user_id)
                .order_by(JobPostingORM.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_to_domain(row) for row in rows]
