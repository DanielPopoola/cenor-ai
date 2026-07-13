from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from common.errors import ConflictError
from common.schemas import APIResponse
from observation.errors import ObservationNotFoundError
from observation.repository import ObservationRepository
from observation.schemas import ObservationResponse
from observation.service import ObservationService
from session.repository import SessionRepository

router = APIRouter()


def get_db(request: Request) -> Iterator[DBSession]:
    yield from request.app.state.database.get_db_session()


@router.get("/{session_id}/observations")
async def get_observations(
    session_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[ObservationResponse]:
    """
    Tenant isolation happens here via SessionRepository.find_session
    (raises SessionNotFoundError -> 404 if not owned by this user),
    since Observation has no user_id column of its own — same pattern
    as session/repository.py's Segment lookups.

    Self-healing fallback: the background Observer task (triggered on
    POST /sessions/{id}/end) can fail silently — a background task
    exception never reaches the client, and there's no queue/retry
    infra behind it (TDD constraint: no managed queue for v1). Rather
    than leave a session stuck 404-ing forever if that happens, this
    route distinguishes two different reasons an Observation might be
    missing:

    - Session still in_progress -> genuinely too early, plain 404.
      This is the expected, valid polling state.
    - Session already completed/abandoned but still no Observation ->
      the background task either never ran or died. Run the Observer
      inline, right here, rather than silently 404-ing forever. This
      trades a slower response on the (rare) retry path for not
      needing a second background-scheduling mechanism.

    If the inline retry itself fails, that's a real, current failure
    the client explicitly asked about and waited for — it propagates
    as a loud error rather than another silent 404.
    """
    session_repository = SessionRepository(db)
    observation_repository = ObservationRepository(db)

    session = session_repository.find_session(user.id, session_id)

    try:
        observation = observation_repository.find_by_session_id(session_id)
    except ObservationNotFoundError:
        if session.status == "in_progress":
            raise

        observation_service = ObservationService(
            session_repository=session_repository,
            observation_repository=observation_repository,
            ai_service=request.app.state.ai_service,
        )
        try:
            observation = await observation_service.run_observation(session_id)
            db.commit()
        except ConflictError:
            # A concurrent request (e.g. another overlapping poll, or
            # the original background task finishing late) already
            # created the Observation between our check and our
            # attempt — that's a success, not a real conflict from
            # this caller's point of view. Re-fetch instead of
            # surfacing a 409 for what is actually the happy path.
            observation = observation_repository.find_by_session_id(session_id)

    return APIResponse.ok(ObservationResponse.from_domain(observation))
