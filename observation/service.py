from ai.protocol import AIService
from observation.domain import Observation
from observation.repository import ObservationRepository
from session.lens import derive_lens_type
from session.repository import SessionRepository
from session.transcript import build_flat_transcript
from common.errors import ValidationError
from common.logger import get_logger

_log = get_logger("observation.service")


class ObservationService:
    """
    Turns a completed session's stored Segments/Turns into a single
    Observer call, and persists the result.
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        observation_repository: ObservationRepository,
        ai_service: AIService | None,
    ):
        self._session_repository = session_repository
        self._observation_repository = observation_repository
        self._ai_service = ai_service

    async def run_observation(self, session_id: str) -> Observation:
        if self._ai_service is None:
            raise ValidationError(
                "AI service is currently unavailable — cannot run the Observer"
            )

        segments = self._session_repository.list_segments_for_session(session_id)
        turns_by_segment = {
            segment.id: self._session_repository.list_turns_for_segment(segment.id)
            for segment in segments
        }
        flat_transcript = build_flat_transcript(segments, turns_by_segment)
        lens_type = derive_lens_type(segments)

        entries = await self._ai_service.run_observer(
            full_transcript=[turn.model_dump() for turn in flat_transcript],
            lens_type=lens_type,
        )

        observation = self._observation_repository.create(
            session_id=session_id, entries=entries
        )
        _log.info(
            "observation_created",
            session_ref=session_id,
            entry_count=len(entries),
            lens_type=lens_type,
        )
        return observation
