from typing import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from common.schemas import APIResponse
from observation.repository import ObservationRepository
from observation.schemas import ObservationResponse
from session.repository import SessionRepository

router = APIRouter()


def get_db(request: Request) -> Iterator[DBSession]:
    yield from request.app.state.database.get_db_session()


@router.get("/{session_id}/observations")
def get_observations(
    session_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[ObservationResponse]:
    session_repository = SessionRepository(db)
    observation_repository = ObservationRepository(db)

    session_repository.find_session(user.id, session_id)
    observation = observation_repository.find_by_session_id(session_id)

    return APIResponse.ok(ObservationResponse.from_domain(observation))
