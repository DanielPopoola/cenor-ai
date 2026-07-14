from typing import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from candidate_profile.repository import CandidateProfileRepository
from common.errors import ConflictError
from common.schemas import APIResponse
from feedback.errors import FeedbackNotFoundError
from feedback.repository import FeedbackRepository
from feedback.schemas import FeedbackResponse
from feedback.service import FeedbackService
from observation.errors import ObservationNotFoundError
from observation.repository import ObservationRepository
from session.repository import SessionRepository

session_feedback_router = APIRouter()
feedback_history_router = APIRouter()


def get_db(request: Request) -> Iterator[DBSession]:
    yield from request.app.state.database.get_db_session()


@session_feedback_router.get("/{session_id}/feedback")
async def get_feedback(
    session_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[FeedbackResponse]:
    session_repository = SessionRepository(db)
    observation_repository = ObservationRepository(db)
    feedback_repository = FeedbackRepository(db)

    session = session_repository.find_session(user.id, session_id)

    try:
        feedback = feedback_repository.find_by_session_id(session_id)
    except FeedbackNotFoundError:
        # Feedback requires Observation to exist first — if it
        # doesn't, this is genuinely too early regardless of session
        # status, and there's nothing to self-heal yet (Observation's
        # own GET endpoint is responsible for healing itself).
        try:
            observation_repository.find_by_session_id(session_id)
        except ObservationNotFoundError:
            raise FeedbackNotFoundError(f"No feedback yet for session_id={session_id}")

        if session.status == "in_progress":
            raise

        candidate_profile_repository = CandidateProfileRepository(db)
        feedback_service = FeedbackService(
            session_repository=session_repository,
            observation_repository=observation_repository,
            feedback_repository=feedback_repository,
            candidate_profile_repository=candidate_profile_repository,
            ai_service=request.app.state.ai_service,
        )
        try:
            feedback = await feedback_service.run_feedback_synthesis(
                user_id=user.id, session_id=session_id
            )
            db.commit()
        except ConflictError:
            # Same race case as observation/routes.py's self-healing
            # path — a concurrent request already created the Feedback
            # row between our check and our attempt.
            feedback = feedback_repository.find_by_session_id(session_id)

    return APIResponse.ok(FeedbackResponse.from_domain(feedback))


@feedback_history_router.get("/history")
def feedback_history(
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[list[FeedbackResponse]]:

    session_repository = SessionRepository(db)
    feedback_repository = FeedbackRepository(db)

    sessions = session_repository.list_sessions(user.id)
    session_order = {session.id: index for index, session in enumerate(sessions)}

    history = feedback_repository.list_by_session_ids(
        [session.id for session in sessions]
    )
    # list_sessions already returns most-recent-first; list_by_session_ids
    # has no defined order (it's an IN query), so re-sort to match.
    history.sort(key=lambda feedback: session_order[feedback.session_id])

    return APIResponse.ok([FeedbackResponse.from_domain(f) for f in history])
