from datetime import datetime

from pydantic import BaseModel, Field

from session.domain import Segment, Session, SessionStatus, StrictnessMode
from session.service import TurnResult


class CreateSessionRequest(BaseModel):
    job_posting_id: str
    duration_limit_minutes: int | None = None  # falls back to Settings default
    strictness_mode: StrictnessMode = "standard"


class SubmitTurnRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    code_snapshot: str | None = Field(default=None, max_length=50_000)


class SegmentResponse(BaseModel):
    """
    Deliberately omits `checklist` — interviewer_system_prompt.md:
    "Never reference the checklist... to the candidate. That machinery
    is invisible to them." That rule governs conversation, but the same
    principle extends here: no legitimate frontend use for exposing a
    live progress score during the interview.
    """

    id: str
    segment_order: int
    area: str
    editor_available: bool
    duration_limit_minutes: int
    status: str

    @classmethod
    def from_domain(cls, segment: Segment) -> "SegmentResponse":
        return cls(
            id=segment.id,
            segment_order=segment.segment_order,
            area=segment.area,
            editor_available=segment.editor_available,
            duration_limit_minutes=segment.duration_limit_minutes,
            status=segment.status,
        )


class SessionResponse(BaseModel):
    id: str
    user_id: str
    job_posting_id: str
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    duration_limit_minutes: int
    strictness_mode: StrictnessMode

    @classmethod
    def from_domain(cls, session: Session) -> "SessionResponse":
        return cls(
            id=session.id,
            user_id=session.user_id,
            job_posting_id=session.job_posting_id,
            status=session.status,
            started_at=session.started_at,
            ended_at=session.ended_at,
            duration_limit_minutes=session.duration_limit_minutes,
            strictness_mode=session.strictness_mode,
        )


class TurnResultResponse(BaseModel):
    session: SessionResponse
    segment: SegmentResponse
    outcome: str
    next_question: str | None

    @classmethod
    def from_domain(cls, result: TurnResult) -> "TurnResultResponse":
        return cls(
            session=SessionResponse.from_domain(result.session),
            segment=SegmentResponse.from_domain(result.segment),
            outcome=result.outcome,
            next_question=result.next_question,
        )
