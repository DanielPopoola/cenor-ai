from ai.prompts.trait_mapping import build_trait_mapping
from ai.protocol import AIService
from candidate_profile.repository import CandidateProfileRepository
from candidate_profile.summary import summarize_for_feedback
from common.errors import ValidationError
from common.logger import get_logger
from feedback.domain import Feedback
from feedback.repository import FeedbackRepository
from observation.repository import ObservationRepository
from session.lens import derive_lens_type
from session.repository import SessionRepository

_log = get_logger("feedback.service")


class FeedbackService:
    """
    Turns a session's Observation output into synthesized trait
    summaries and focus points, and persists the result.
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        observation_repository: ObservationRepository,
        feedback_repository: FeedbackRepository,
        candidate_profile_repository: CandidateProfileRepository,
        ai_service: AIService | None,
    ):
        self._session_repository = session_repository
        self._observation_repository = observation_repository
        self._feedback_repository = feedback_repository
        self._candidate_profile_repository = candidate_profile_repository
        self._ai_service = ai_service

    async def run_feedback_synthesis(self, user_id: str, session_id: str) -> Feedback:
        if self._ai_service is None:
            raise ValidationError(
                "AI service is currently unavailable — cannot run the Feedback Synthesizer"
            )

        self._session_repository.find_session(user_id, session_id)

        observation = self._observation_repository.find_by_session_id(session_id)

        segments = self._session_repository.list_segments_for_session(session_id)
        lens_type = derive_lens_type(segments)
        trait_mapping = build_trait_mapping(lens_type)

        profile = self._candidate_profile_repository.find_by_user_id_or_none(user_id)
        candidate_profile_summary = (
            summarize_for_feedback(profile) if profile is not None else ""
        )

        result = await self._ai_service.run_feedback_synthesis(
            observations=observation.entries,
            lens_type=lens_type,
            trait_mapping=trait_mapping,
            candidate_profile_summary=candidate_profile_summary,
        )

        feedback = self._feedback_repository.create(
            session_id=session_id,
            trait_summary=result.trait_summary,
            focus_points=result.focus_points,
        )
        _log.info(
            "feedback_created",
            session_ref=session_id,
            trait_count=len(result.trait_summary),
            focus_point_count=len(result.focus_points),
            lens_type=lens_type,
        )
        return feedback
