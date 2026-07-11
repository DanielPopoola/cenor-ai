from typing import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from job_posting.repository import JobPostingRepository
from job_posting.schemas import CreateJobPostingRequest, JobPostingResponse
from job_posting.service import JobPostingService
from common.schemas import APIResponse

router = APIRouter()


def get_db(request: Request) -> Iterator[DBSession]:
    yield from request.app.state.database.get_db_session()


def get_job_posting_service(db: DBSession = Depends(get_db)) -> JobPostingService:
    return JobPostingService(JobPostingRepository(db))


@router.post("")
def create_job_posting(
    body: CreateJobPostingRequest,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: JobPostingService = Depends(get_job_posting_service),
) -> APIResponse[JobPostingResponse]:
    job = service.create(
        user_id=user.id,
        title=body.title,
        description_raw=body.description_raw,
        company=body.company,
        url=body.url,
    )
    db.commit()
    return APIResponse.ok(JobPostingResponse(**job.model_dump()))


@router.get("")
def list_job_postings(
    user: User = Depends(get_current_user),
    service: JobPostingService = Depends(get_job_posting_service),
) -> APIResponse[list[JobPostingResponse]]:
    jobs = service.list_for_user(user.id)
    return APIResponse.ok([JobPostingResponse(**job.model_dump()) for job in jobs])


@router.get("/{job_posting_id}")
def get_job_posting(
    job_posting_id: str,
    user: User = Depends(get_current_user),
    service: JobPostingService = Depends(get_job_posting_service),
) -> APIResponse[JobPostingResponse]:
    job = service.get(user.id, job_posting_id)
    return APIResponse.ok(JobPostingResponse(**job.model_dump()))
