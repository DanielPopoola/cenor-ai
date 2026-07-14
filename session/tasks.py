from ai.protocol import AIService
from candidate_profile.repository import CandidateProfileRepository
from config import Settings
from db.session import Database
from feedback.repository import FeedbackRepository
from feedback.service import FeedbackService
from observation.repository import ObservationRepository
from observation.service import ObservationService
from session.repository import SessionRepository


async def run_observation_task(
    session_id: str,
    user_id: str,
    database: Database,
    ai_service: AIService | None,
    settings: Settings,
) -> None:
    with database.session_scope() as db:
        session_repository = SessionRepository(db)
        observation_repository = ObservationRepository(db)

        observation_service = ObservationService(
            session_repository=session_repository,
            observation_repository=observation_repository,
            ai_service=ai_service,
            observer_variant=settings.observer_prompt_variant,
        )
        await observation_service.run_observation(session_id)

        feedback_service = FeedbackService(
            session_repository=session_repository,
            observation_repository=observation_repository,
            feedback_repository=FeedbackRepository(db),
            candidate_profile_repository=CandidateProfileRepository(db),
            ai_service=ai_service,
        )
        await feedback_service.run_feedback_synthesis(
            user_id=user_id, session_id=session_id
        )
