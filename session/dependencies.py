from observation.repository import ObservationRepository
from typing import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DBSession

from candidate_profile.repository import CandidateProfileRepository
from config import Settings
from job_posting.repository import JobPostingRepository
from observation.service import ObservationService
from session.repository import SessionRepository
from session.service import SessionService

router = APIRouter()


def get_db(request: Request) -> Iterator[DBSession]:
    yield from request.app.state.database.get_db_session()


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_session_service(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    db: DBSession = Depends(get_db),
) -> SessionService:
    return SessionService(
        settings=settings,
        repository=SessionRepository(db),
        candidate_profile_repository=CandidateProfileRepository(db),
        job_posting_repository=JobPostingRepository(db),
        ai_service=request.app.state.ai_service,
    )


def get_observation_service(
    request: Request,
    db: DBSession = Depends(get_db),
) -> ObservationService:
    return ObservationService(
        session_repository=SessionRepository(db),
        observation_repository=ObservationRepository(db),
        ai_service=request.app.state.ai_service,
    )
