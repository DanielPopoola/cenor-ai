from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from session.domain import Segment, SegmentChecklist, Session, Turn
from session.errors import SegmentNotFoundError, SessionNotFoundError
from session.models import SegmentORM, SessionORM, TurnORM


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _session_to_domain(row: SessionORM) -> Session:
    return Session(
        id=row.id,
        user_id=row.user_id,
        job_posting_id=row.job_posting_id,
        status=row.status,  # type: ignore
        started_at=_as_utc(row.started_at),  # type: ignore
        ended_at=_as_utc(row.ended_at),
        duration_limit_minutes=row.duration_limit_minutes,
        strictness_mode=row.strictness_mode,  # type: ignore
    )


def _segment_to_domain(row: SegmentORM) -> Segment:
    return Segment(
        id=row.id,
        session_id=row.session_id,
        segment_order=row.segment_order,
        area=row.area,  # type: ignore
        editor_available=row.editor_available,
        duration_limit_minutes=row.duration_limit_minutes,
        checklist=SegmentChecklist.model_validate_json(row.checklist),
        status=row.status,  # type: ignore
        started_at=_as_utc(row.started_at),
    )


def _turn_to_domain(row: TurnORM) -> Turn:
    return Turn(
        id=row.id,
        segment_id=row.segment_id,
        turn_number=row.turn_number,
        speaker=row.speaker,  # type: ignore
        content=row.content,
        code_snapshot=row.code_snapshot,
        created_at=_as_utc(row.created_at),  # type: ignore
    )


class SessionRepository:
    def __init__(self, db: DBSession):
        self._db = db

    # --- Session -----------------------------------------------------

    def create_session(
        self,
        user_id: str,
        job_posting_id: str,
        duration_limit_minutes: int,
        strictness_mode: str,
    ) -> Session:
        row = SessionORM(
            user_id=user_id,
            job_posting_id=job_posting_id,
            duration_limit_minutes=duration_limit_minutes,
            strictness_mode=strictness_mode,
        )
        self._db.add(row)
        self._db.flush()
        return _session_to_domain(row)

    def find_session(self, user_id: str, session_id: str) -> Session:
        row = self._db.execute(
            select(SessionORM).where(
                SessionORM.id == session_id, SessionORM.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is None:
            raise SessionNotFoundError(
                f"No session id={session_id} for user_id={user_id}"
            )
        return _session_to_domain(row)

    def list_sessions(self, user_id: str) -> list[Session]:
        rows = (
            self._db.execute(
                select(SessionORM)
                .where(SessionORM.user_id == user_id)
                .order_by(SessionORM.started_at.desc())
            )
            .scalars()
            .all()
        )
        return [_session_to_domain(row) for row in rows]

    def update_session_status(
        self, user_id: str, session_id: str, status: str, ended_at=None
    ) -> Session:
        row = self._get_session_row(user_id, session_id)
        row.status = status
        if ended_at is not None:
            row.ended_at = ended_at
        self._db.flush()
        return _session_to_domain(row)

    def _get_session_row(self, user_id: str, session_id: str) -> SessionORM:
        row = self._db.execute(
            select(SessionORM).where(
                SessionORM.id == session_id, SessionORM.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is None:
            raise SessionNotFoundError(
                f"No session id={session_id} for user_id={user_id}"
            )
        return row

    # --- Segment -------------------------------------------------------
    # Segment lookups don't take user_id directly — they're always
    # reached through an already-tenant-checked Session (service layer
    # calls find_session first). segment_id alone is not guessable/
    # enumerable in a way that matters without the parent session_id.

    def create_segment(
        self,
        session_id: str,
        segment_order: int,
        area: str,
        editor_available: bool,
        duration_limit_minutes: int,
    ) -> Segment:
        row = SegmentORM(
            session_id=session_id,
            segment_order=segment_order,
            area=area,
            editor_available=editor_available,
            duration_limit_minutes=duration_limit_minutes,
            checklist=SegmentChecklist().model_dump_json(),
        )
        self._db.add(row)
        self._db.flush()
        return _segment_to_domain(row)

    def find_segment(self, segment_id: str) -> Segment:
        row = self._db.get(SegmentORM, segment_id)
        if row is None:
            raise SegmentNotFoundError(f"No segment id={segment_id}")
        return _segment_to_domain(row)

    def list_segments_for_session(self, session_id: str) -> list[Segment]:
        rows = (
            self._db.execute(
                select(SegmentORM)
                .where(SegmentORM.session_id == session_id)
                .order_by(SegmentORM.segment_order.asc())
            )
            .scalars()
            .all()
        )
        return [_segment_to_domain(row) for row in rows]

    def update_segment(
        self,
        segment_id: str,
        checklist: SegmentChecklist,
        status: str,
        started_at=None,
    ) -> Segment:
        row = self._db.get(SegmentORM, segment_id)
        if row is None:
            raise SegmentNotFoundError(f"No segment id={segment_id}")
        row.checklist = checklist.model_dump_json()
        row.status = status
        if started_at is not None:
            row.started_at = started_at
        self._db.flush()
        return _segment_to_domain(row)

    # --- Turn ------------------------------------------------------------

    def create_turn(
        self,
        segment_id: str,
        turn_number: int,
        speaker: str,
        content: str,
        code_snapshot: str | None = None,
    ) -> Turn:
        row = TurnORM(
            segment_id=segment_id,
            turn_number=turn_number,
            speaker=speaker,
            content=content,
            code_snapshot=code_snapshot,
        )
        self._db.add(row)
        self._db.flush()
        return _turn_to_domain(row)

    def list_turns_for_segment(self, segment_id: str) -> list[Turn]:
        rows = (
            self._db.execute(
                select(TurnORM)
                .where(TurnORM.segment_id == segment_id)
                .order_by(TurnORM.turn_number.asc())
            )
            .scalars()
            .all()
        )
        return [_turn_to_domain(row) for row in rows]

    def find_last_candidate_turn(self, segment_id: str) -> Turn | None:
        row = self._db.execute(
            select(TurnORM)
            .where(TurnORM.segment_id == segment_id, TurnORM.speaker == "candidate")
            .order_by(TurnORM.turn_number.desc())
            .limit(1)
        ).scalar_one_or_none()
        return _turn_to_domain(row) if row is not None else None
