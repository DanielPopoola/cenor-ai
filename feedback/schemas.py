from datetime import datetime

from pydantic import BaseModel

from feedback.domain import Feedback


class TraitSummaryResponse(BaseModel):
    """
    source_observations is internal-only per
    feedback_synthesizer_prompt_draft.md ("never rendered to the
    candidate") — included here anyway since it's a plain list of ints
    with no sensitive content, and a frontend may reasonably want to
    let a candidate click through from a trait summary to the
    Observer entries that back it. If that turns out to be unwanted,
    trimming it is a one-line change here, not a re-architecture.
    """

    trait: str
    summary: str
    source_observations: list[int]


class FocusPointResponse(BaseModel):
    pattern: str
    resource: str
    source_observations: list[int]


class FeedbackResponse(BaseModel):
    id: str
    session_id: str
    trait_summary: list[TraitSummaryResponse]
    focus_points: list[FocusPointResponse]
    created_at: datetime

    @classmethod
    def from_domain(cls, feedback: Feedback) -> "FeedbackResponse":
        return cls(
            id=feedback.id,
            session_id=feedback.session_id,
            trait_summary=[
                TraitSummaryResponse(**t.model_dump()) for t in feedback.trait_summary
            ],
            focus_points=[
                FocusPointResponse(**f.model_dump()) for f in feedback.focus_points
            ],
            created_at=feedback.created_at,
        )
