from dataclasses import dataclass
from datetime import datetime, timezone

from ai.protocol import AIService
from candidate_profile.domain import CandidateProfile
from candidate_profile.repository import CandidateProfileRepository
from common.errors import ValidationError
from common.logger import get_logger
from common.sanitize import sanitize_candidate_answer, sanitize_code_snapshot
from config import Settings
from job_posting.domain import JobPosting
from job_posting.repository import JobPostingRepository
from session.domain import InterviewerTurnResponse, Segment, Session
from session.errors import (
    CandidateProfileIncompleteError,
    SessionNotInProgressError,
)
from session.repository import SessionRepository
from session.session_setup import build_default_segments

_log = get_logger("session.service")


@dataclass(frozen=True)
class TurnResult:
    session: Session
    segment: Segment
    outcome: str  # "continue" | "segment_transitioned" | "session_completed"
    next_question: str | None
    just_completed: bool = False
    """True only when this call is what caused status to become
    "completed" — lets the route layer schedule the Observer background
    task exactly once, the same way POST /end already does, without
    SessionService itself knowing about BackgroundTasks/app state."""


@dataclass(frozen=True)
class EndSessionResult:
    session: Session
    just_completed: bool


class SessionService:
    def __init__(
        self,
        settings: Settings,
        repository: SessionRepository,
        candidate_profile_repository: CandidateProfileRepository,
        job_posting_repository: JobPostingRepository,
        ai_service: AIService | None,
    ):
        self._settings = settings
        self._repository = repository
        self._candidate_profile_repository = candidate_profile_repository
        self._job_posting_repository = job_posting_repository
        self._ai_service = ai_service

    def _build_candidate_context(self, user_id: str) -> dict:
        """
        Session creation already gates on cv_status == 'done', so a
        profile with a usable cv_structured should always exist here —
        but that invariant is enforced elsewhere (create_session), not
        by this method, so we fail loudly rather than silently sending
        the LLM an empty context if it's ever violated.
        """
        profile = self._candidate_profile_repository.find_by_user_id_or_none(user_id)
        if profile is None or profile.cv_structured is None:
            raise ValidationError(
                "Candidate profile is missing required CV context for this session"
            )
        return self._candidate_context_dict(profile)

    @staticmethod
    def _candidate_context_dict(profile: CandidateProfile) -> dict:
        context: dict = {"cv": profile.cv_structured.model_dump(mode="json")}  # type: ignore
        if profile.github_structured is not None:
            context["github"] = profile.github_structured.model_dump()
        return context

    def _build_job_context(self, user_id: str, job_posting_id: str) -> dict:
        job = self._job_posting_repository.find_by_id(user_id, job_posting_id)
        return self._job_context_dict(job)

    @staticmethod
    def _job_context_dict(job: JobPosting) -> dict:
        return {
            "title": job.title,
            "company": job.company,
            "description": job.description_raw,
        }

    # --- Session creation -----------------------------------------------

    async def create_session(
        self,
        user_id: str,
        job_posting_id: str,
        duration_limit_minutes: int | None = None,
        strictness_mode: str = "standard",
    ) -> tuple[Session, Segment, TurnResult]:
        """
        Returns (session, first_segment, turn_result). Blocked with
        CandidateProfileIncompleteError (403 at the route layer) until
        cv_status == "done" — TDD "POST /sessions returns 403 if
        cv_structured is null" (extended here to the completeness bar,
        not just null-check, matching cv_status's own definition).
        """
        duration = duration_limit_minutes or self._settings.session_length_default
        self._validate_duration(duration)

        profile = self._candidate_profile_repository.find_by_user_id_or_none(user_id)
        if profile is None or profile.cv_status != "done":
            raise CandidateProfileIncompleteError(
                "A complete CV is required before starting a session"
            )

        # Raises JobPostingNotFoundError (404) if not owned by this user
        # — tenant isolation enforced by the repository itself.
        self._job_posting_repository.find_by_id(user_id, job_posting_id)

        session = self._repository.create_session(
            user_id=user_id,
            job_posting_id=job_posting_id,
            duration_limit_minutes=duration,
            strictness_mode=strictness_mode,
        )

        specs = build_default_segments(duration)
        segments = [
            self._repository.create_segment(
                session_id=session.id,
                segment_order=order,
                area=spec.area,
                editor_available=spec.editor_available,
                duration_limit_minutes=spec.duration_limit_minutes,
            )
            for order, spec in enumerate(specs)
        ]

        first_segment = self._repository.update_segment(
            segment_id=segments[0].id,
            checklist=segments[0].checklist,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )

        result = await self._run_interviewer(
            user_id=user_id, session=session, segment=first_segment
        )
        # A brand-new segment completing on its very first (opening)
        # call would be unusual — a fresh checklist starts all not_yet —
        # but not impossible if time_limit is absurdly low; surfacing it
        # as a clean TurnResult rather than asserting it can't happen.
        return session, result.segment, result

    def _validate_duration(self, duration_limit_minutes: int) -> None:
        if not (
            self._settings.session_length_min
            <= duration_limit_minutes
            <= self._settings.session_length_max
        ):
            raise ValidationError(
                f"duration_limit_minutes must be between "
                f"{self._settings.session_length_min} and "
                f"{self._settings.session_length_max}"
            )

    # --- Turn submission --------------------------------------------------

    async def submit_turn(
        self,
        user_id: str,
        session_id: str,
        content: str,
        code_snapshot: str | None = None,
    ) -> TurnResult:
        session = self._apply_lazy_abandonment_check(user_id, session_id)
        if session.status != "in_progress":
            raise SessionNotInProgressError(
                f"Session {session_id} is not in progress (status={session.status})"
            )

        segments = self._repository.list_segments_for_session(session_id)
        current_segment = next(s for s in segments if s.status == "in_progress")

        sanitized_content = sanitize_candidate_answer(content, self._settings)
        sanitized_code = (
            sanitize_code_snapshot(code_snapshot, self._settings)
            if code_snapshot is not None
            else None
        )

        existing_turns = self._repository.list_turns_for_segment(current_segment.id)
        self._repository.create_turn(
            segment_id=current_segment.id,
            turn_number=len(existing_turns) + 1,
            speaker="candidate",
            content=sanitized_content,
            code_snapshot=sanitized_code,
        )

        return await self._run_interviewer(
            user_id=user_id, session=session, segment=current_segment
        )

    async def start_next_question(self, user_id: str, session_id: str) -> TurnResult:
        """
        Called after a "segment_transitioned" outcome to get the new
        segment's opening question. Kept as its own call (not
        auto-chained inside submit_turn) so a segment boundary never
        triggers a second LLM call within the same request — keeps
        per-request latency bounded to one Interviewer call, and gives
        the frontend a natural point to show a transition ("moving to
        the next section...") before the new question appears.
        """
        session = self._apply_lazy_abandonment_check(user_id, session_id)
        if session.status != "in_progress":
            raise SessionNotInProgressError(
                f"Session {session_id} is not in progress (status={session.status})"
            )

        segments = self._repository.list_segments_for_session(session_id)
        current_segment = next(s for s in segments if s.status == "in_progress")
        return await self._run_interviewer(
            user_id=user_id, session=session, segment=current_segment
        )

    async def _run_interviewer(
        self, user_id: str, session: Session, segment: Segment
    ) -> TurnResult:
        """
        Calls the Interviewer for the given segment, persists its next
        question as a Turn, updates the checklist, and applies the
        deterministic time-based completion override. Does NOT chain
        into the next segment on completion — that's the caller's job
        via start_next_question(), see its docstring for why.
        """
        if self._ai_service is None:
            raise ValidationError(
                "AI service is currently unavailable — please try again shortly"
            )

        last_candidate_turn = self._repository.find_last_candidate_turn(segment.id)

        candidate_context = self._build_candidate_context(user_id)
        job_context = self._build_job_context(user_id, session.job_posting_id)

        llm_response: InterviewerTurnResponse = (
            await self._ai_service.run_interviewer_turn(
                candidate_context=candidate_context,
                job_context=job_context,
                strictness_mode=session.strictness_mode,
                segment_area=segment.area,
                editor_available=segment.editor_available,
                current_checklist=segment.checklist.model_dump(),
                last_candidate_turn_content=(
                    last_candidate_turn.content if last_candidate_turn else None
                ),
                last_code_snapshot=(
                    last_candidate_turn.code_snapshot if last_candidate_turn else None
                ),
            )
        )

        time_expired = self._segment_time_expired(segment)
        segment_complete = llm_response.segment_complete or time_expired

        updated_segment = self._repository.update_segment(
            segment_id=segment.id,
            checklist=llm_response.updated_checklist,
            status="completed" if segment_complete else "in_progress",
        )

        if not segment_complete:
            self._repository.create_turn(
                segment_id=segment.id,
                turn_number=len(self._repository.list_turns_for_segment(segment.id))
                + 1,
                speaker="interviewer",
                content=llm_response.next_question,
            )
            return TurnResult(
                session=session,
                segment=updated_segment,
                outcome="continue",
                next_question=llm_response.next_question,
            )

        return await self._complete_segment_and_stop(user_id, session, updated_segment)

    def _segment_time_expired(self, segment: Segment) -> bool:
        if segment.started_at is None:
            return False
        elapsed = datetime.now(timezone.utc) - segment.started_at
        return elapsed.total_seconds() >= segment.duration_limit_minutes * 60

    async def _complete_segment_and_stop(
        self, user_id: str, session: Session, completed_segment: Segment
    ) -> TurnResult:
        """
        Starts the next pending segment (if any) but stops short of
        calling the Interviewer for it — see start_next_question(). If
        there's no next segment, ends the whole session instead (the
        one-sitting model, Section 2a: one Session moves through all
        its Segments before ending, no separate session per area).
        """
        segments = self._repository.list_segments_for_session(session.id)
        remaining = [
            s for s in segments if s.segment_order > completed_segment.segment_order
        ]

        if not remaining:
            completed_session = self._repository.update_session_status(
                user_id=user_id,
                session_id=session.id,
                status="completed",
                ended_at=datetime.now(timezone.utc),
            )
            return TurnResult(
                session=completed_session,
                segment=completed_segment,
                outcome="session_completed",
                next_question=None,
                just_completed=True,
            )

        next_segment = self._repository.update_segment(
            segment_id=remaining[0].id,
            checklist=remaining[0].checklist,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        return TurnResult(
            session=session,
            segment=next_segment,
            outcome="segment_transitioned",
            next_question=None,
        )

    # --- Lazy abandonment -------------------------------------------------

    def _apply_lazy_abandonment_check(self, user_id: str, session_id: str) -> Session:
        """
        No cron/background sweep (TDD "Session abandonment rule") — a
        session past its deadline is treated as abandoned the moment
        it's read or a turn is submitted against it, computed here,
        not on a timer.
        """
        session = self._repository.find_session(user_id, session_id)
        if session.status != "in_progress":
            return session

        deadline = session.started_at.timestamp() + session.duration_limit_minutes * 60
        if datetime.now(timezone.utc).timestamp() > deadline:
            return self._repository.update_session_status(
                user_id=user_id,
                session_id=session_id,
                status="abandoned",
                ended_at=datetime.now(timezone.utc),
            )
        return session

    # --- Reads -----------------------------------------------------------

    def get_session(self, user_id: str, session_id: str) -> Session:
        return self._apply_lazy_abandonment_check(user_id, session_id)

    def list_sessions(self, user_id: str) -> list[Session]:
        return self._repository.list_sessions(user_id)

    def end_session(self, user_id: str, session_id: str) -> EndSessionResult:
        session = self._repository.find_session(user_id, session_id)
        if session.status != "in_progress":
            # Already completed/abandoned — a no-op. just_completed=False
            # tells the route not to re-trigger the Observer chain.
            return EndSessionResult(session=session, just_completed=False)
        completed = self._repository.update_session_status(
            user_id=user_id,
            session_id=session_id,
            status="completed",
            ended_at=datetime.now(timezone.utc),
        )
        return EndSessionResult(session=completed, just_completed=True)
