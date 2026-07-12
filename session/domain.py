from datetime import datetime
from typing import Literal

from pydantic import BaseModel

BehaviorStatus = Literal["not_yet", "partial", "demonstrated"]

SegmentArea = Literal[
    "programming_algorithms",
    "frameworks_tools",
    "specialized",
    "system_design",
]

SessionStatus = Literal["in_progress", "completed", "abandoned"]
SegmentStatus = Literal["pending", "in_progress", "completed"]
StrictnessMode = Literal["strict", "standard", "lenient"]
Speaker = Literal["interviewer", "candidate"]


class SegmentChecklist(BaseModel):
    """
    The 5 behaviors the Interviewer tracks live, per segment (Section
    2a). `code_matches_plan` is deliberately absent — it's a 6th
    category, but Observer-only; the Interviewer never reasons about it
    (see interviewer_system_prompt.md). Fresh per segment, since domain
    knowledge gaps cause behavior gaps — the same candidate can be
    strong here and weak there.
    """

    clarifies_ambiguity: BehaviorStatus = "not_yet"
    reasons_through_examples: BehaviorStatus = "not_yet"
    chooses_approach_intentionally: BehaviorStatus = "not_yet"
    tests_and_catches_issues: BehaviorStatus = "not_yet"
    communicates_thinking: BehaviorStatus = "not_yet"

    @property
    def all_demonstrated(self) -> bool:
        return all(
            status == "demonstrated"
            for status in (
                self.clarifies_ambiguity,
                self.reasons_through_examples,
                self.chooses_approach_intentionally,
                self.tests_and_catches_issues,
                self.communicates_thinking,
            )
        )


class Turn(BaseModel):
    id: str
    segment_id: str  # Turn belongs to a Segment, not directly to Session
    turn_number: int
    speaker: Speaker
    content: str
    code_snapshot: str | None = None  # editor-available segments only
    created_at: datetime


class Segment(BaseModel):
    id: str
    session_id: str
    segment_order: int
    area: SegmentArea
    editor_available: bool  # only true for programming_algorithms in v1
    duration_limit_minutes: int
    checklist: SegmentChecklist = SegmentChecklist()
    status: SegmentStatus = "pending"
    started_at: datetime | None = None  # set when the segment becomes in_progress


class Session(BaseModel):
    id: str
    user_id: str
    job_posting_id: str
    status: SessionStatus = "in_progress"
    started_at: datetime
    ended_at: datetime | None = None
    duration_limit_minutes: int
    strictness_mode: StrictnessMode = "standard"  # global per session, per Section 2a


class InterviewerTurnResponse(BaseModel):
    """
    Shape returned by ai.run_interviewer_turn each turn. `reasoning`
    and `updated_checklist` are internal-only, never shown to the
    candidate — only `next_question` is (interviewer_system_prompt.md
    "Output format"). When segment_complete is True, next_question is
    an empty string; a separate step handles the transition.
    """

    next_question: str
    updated_checklist: SegmentChecklist
    segment_complete: bool
    reasoning: str
