from ai.protocol import AIService
from config import Settings
from db.session import Database
from observation.repository import ObservationRepository
from observation.service import ObservationService
from session.repository import SessionRepository


async def run_observation_task(
    session_id: str,
    database: Database,
    ai_service: AIService | None,
    settings: Settings,
) -> None:
    """
    Runs after the HTTP response for POST /sessions/{id}/end has
    already been sent (FastAPI BackgroundTasks semantics). The
    request's own `Depends(get_db)` session is closed by that point,
    so this opens a fresh one via Database.session_scope() rather than
    reusing anything built during the request — passing an
    already-scoped ObservationService in from the route would hand the
    task a repository wrapping a dead session.
    """
    with database.session_scope() as db:
        service = ObservationService(
            session_repository=SessionRepository(db),
            observation_repository=ObservationRepository(db),
            ai_service=ai_service,
            observer_variant=settings.observer_prompt_variant,
        )
        await service.run_observation(session_id)
