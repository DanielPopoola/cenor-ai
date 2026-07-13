from datetime import datetime

from pydantic import BaseModel

from observation.domain import Observation, ObservationCategory


class ObservationEntryResponse(BaseModel):
    """
    Exposes id/category/fact/turn_ref as-is. Unlike Feedback's
    source_observations (which cite these ids only for internal
    traceability, never rendered to the candidate — see
    feedback_synthesizer_prompt_draft.md), this endpoint's whole
    purpose IS showing the candidate their own observations, so
    nothing here needs to be trimmed.
    """

    id: int
    category: ObservationCategory
    fact: str
    turn_ref: list[int]


class ObservationResponse(BaseModel):
    id: str
    session_id: str
    entries: list[ObservationEntryResponse]
    created_at: datetime

    @classmethod
    def from_domain(cls, observation: Observation) -> "ObservationResponse":
        return cls(
            id=observation.id,
            session_id=observation.session_id,
            entries=[
                ObservationEntryResponse(**e.model_dump()) for e in observation.entries
            ],
            created_at=observation.created_at,
        )
