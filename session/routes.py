from typing import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from candidate_profile.repository import CandidateProfileRepository
from common.schemas import APIResponse
from config import Settings
from job_posting.repository import JobPostingRepository
from session.repository import SessionRepository
from session.schemas import (
    CreateSessionRequest,
    SessionResponse,
    SubmitTurnRequest,
    TurnResultResponse,
)
from session.service import SessionService
from session.tasks import run_observation_task

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


@router.post("")
async def create_session(
    body: CreateSessionRequest,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> APIResponse[TurnResultResponse]:
    session, _first_segment, result = await service.create_session(
        user_id=user.id,
        job_posting_id=body.job_posting_id,
        duration_limit_minutes=body.duration_limit_minutes,
        strictness_mode=body.strictness_mode,
    )
    db.commit()
    return APIResponse.ok(TurnResultResponse.from_domain(result))


@router.post("/{session_id}/turns")
async def submit_turn(
    session_id: str,
    body: SubmitTurnRequest,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> APIResponse[TurnResultResponse]:
    result = await service.submit_turn(
        user_id=user.id,
        session_id=session_id,
        content=body.content,
        code_snapshot=body.code_snapshot,
    )
    db.commit()
    return APIResponse.ok(TurnResultResponse.from_domain(result))


@router.post("/{session_id}/next-question")
async def next_question(
    session_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> APIResponse[TurnResultResponse]:
    result = await service.start_next_question(user_id=user.id, session_id=session_id)
    db.commit()
    return APIResponse.ok(TurnResultResponse.from_domain(result))


@router.post("/{session_id}/end")
def end_session(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> APIResponse[SessionResponse]:
    result = service.end_session(user.id, session_id)
    db.commit()

    if result.just_completed:
        background_tasks.add_task(
            run_observation_task,
            session_id,
            user.id,
            request.app.state.database,
            request.app.state.ai_service,
            request.app.state.settings,
        )

    return APIResponse.ok(SessionResponse.from_domain(result.session))


@router.get("")
def list_sessions(
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> APIResponse[list[SessionResponse]]:
    sessions = service.list_sessions(user.id)
    return APIResponse.ok([SessionResponse.from_domain(s) for s in sessions])


@router.get("/{session_id}")
def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> APIResponse[SessionResponse]:
    session = service.get_session(user.id, session_id)
    return APIResponse.ok(SessionResponse.from_domain(session))
