from typing import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from candidate_profile.repository import CandidateProfileRepository
from common.errors import ValidationError
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
from web.templating import is_htmx, templates

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


def _render_turn_result(request: Request, result) -> Response:
    """
    Shared rendering for any TurnResult reached via an HTMX request —
    used by both submit_turn and next_question, since both can produce
    any of the 3 outcomes. Business logic (the service call) always
    happens before this is reached; this function only decides how to
    show what already happened.
    """
    if result.outcome == "session_completed":
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = f"/sessions/{result.session.id}/feedback"
        return response

    if result.outcome == "segment_transitioned":
        return templates.TemplateResponse(
            request,
            "session/_segment_transition.html",
            {"session": result.session, "next_area": result.segment.area},
        )

    return templates.TemplateResponse(
        request,
        "session/_turn.html",
        {
            "session": result.session,
            "segment": result.segment,
            "question": result.next_question,
        },
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


@router.post("/{session_id}/turns", response_model=None)
async def submit_turn(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> Response | APIResponse[TurnResultResponse]:
    if is_htmx(request):
        form = await request.form()
        raw_content = form.get("content", "")
        raw_code_snapshot = form.get("code_snapshot")
        try:
            validated = SubmitTurnRequest(
                content=str(raw_content),
                code_snapshot=str(raw_code_snapshot) if raw_code_snapshot else None,
            )
        except PydanticValidationError as exc:
            raise ValidationError(str(exc)) from exc
        content = validated.content
        code_snapshot = validated.code_snapshot
    else:
        try:
            body = SubmitTurnRequest.model_validate(await request.json())
        except PydanticValidationError as exc:
            raise ValidationError(str(exc)) from exc
        content = body.content
        code_snapshot = body.code_snapshot

    result = await service.submit_turn(
        user_id=user.id,
        session_id=session_id,
        content=content,
        code_snapshot=code_snapshot,
    )
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

    if is_htmx(request):
        return _render_turn_result(request, result)
    return APIResponse.ok(TurnResultResponse.from_domain(result))


@router.post("/{session_id}/next-question", response_model=None)
async def next_question(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> Response | APIResponse[TurnResultResponse]:
    result = await service.start_next_question(user_id=user.id, session_id=session_id)
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

    if is_htmx(request):
        return _render_turn_result(request, result)
    return APIResponse.ok(TurnResultResponse.from_domain(result))


@router.post("/{session_id}/end", response_model=None)
def end_session(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> Response | APIResponse[SessionResponse]:
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

    if is_htmx(request):
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = f"/sessions/{session_id}/feedback"
        return response

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
