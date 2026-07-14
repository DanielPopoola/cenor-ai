from datetime import datetime

from pydantic import BaseModel


class TraitSummary(BaseModel):
    """
    One trait-level evaluation, grouping Observer entries assigned to
    that trait's categories via the trait mapping
    (ai/prompts/trait_mapping.py). Unlike Observer entries, `summary`
    IS an evaluation — NVC permits this here, provided it stays
    time/context-specific ("in this session, the candidate did X"),
    never a static identity claim (TDD Resolved Issues:
    "Feedback Synthesizer design").

    `source_observations` is a list of ObservationEntry.id values
    (plain int, not a typed cross-domain reference — this is an
    internal traceability citation, not an enforced foreign key) that
    back this summary. Internal-only: never rendered to the candidate
    (feedback_synthesizer_prompt_draft.md).
    """

    trait: str
    summary: str
    source_observations: list[int]


class FocusPoint(BaseModel):
    """
    A forward-looking, growth-framed pattern paired with a concrete
    resource — never a bare deficiency label
    (feedback_synthesizer_prompt_draft.md). `resource` may be a named,
    specific title (book/article) when the Synthesizer is confident
    it's real, or a topic-area description when it isn't — the
    "resource honesty" guardrail against fabricating plausible-sounding
    but nonexistent titles.
    """

    pattern: str
    resource: str
    source_observations: list[int]


class FeedbackResult(BaseModel):
    """
    The Feedback Synthesizer's raw output shape — trait_summary and
    focus_points only, no id/session_id/created_at yet. Distinct from
    Feedback (the persisted, 1:1-with-Session record) the same way
    ObservationEntry is distinct from Observation: this is what the AI
    call returns; feedback/service.py attaches session identity and
    persists it via FeedbackRepository.create(), which is what
    actually produces a Feedback.
    """

    trait_summary: list[TraitSummary]
    focus_points: list[FocusPoint]


class Feedback(BaseModel):
    """
    1:1 with Session, follows Observation (TDD Data Model). Produced
    once, after the Observer has run — the second and final stage of
    the NVC pipeline. Both trait_summary and focus_points may be
    shorter than their "full" set, including empty — zero backing
    observations for a trait, or zero focus points overall, are valid,
    expected outcomes (same principle as the Observer's zero-entries
    case), not something to pad or fabricate around.
    """

    id: str
    session_id: str
    trait_summary: list[TraitSummary]
    focus_points: list[FocusPoint]
    created_at: datetime
