import json
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from common.errors import ConflictError
from feedback.domain import Feedback, FocusPoint, TraitSummary
from feedback.errors import FeedbackNotFoundError
from feedback.models import FeedbackORM


def _as_utc(created_at):
    if created_at.tzinfo is not None:
        return created_at
    return created_at.replace(tzinfo=timezone.utc)


def _to_domain(row: FeedbackORM) -> Feedback:
    return Feedback(
        id=row.id,
        session_id=row.session_id,
        trait_summary=[
            TraitSummary.model_validate(e) for e in json.loads(row.trait_summary_raw)
        ],
        focus_points=[
            FocusPoint.model_validate(e) for e in json.loads(row.focus_points_raw)
        ],
        created_at=_as_utc(row.created_at),
    )


class FeedbackRepository:
    """
    Write-once: no update method exists. Feedback is produced a single
    time by the Feedback Synthesizer, after Observation exists, and
    never mutated afterward. Tenant isolation is NOT enforced here
    directly — same pattern as ObservationRepository: callers are
    expected to have already verified session ownership via
    SessionRepository.find_session(user_id, session_id).
    """

    def __init__(self, db: DBSession):
        self._db = db

    def create(
        self,
        session_id: str,
        trait_summary: list[TraitSummary],
        focus_points: list[FocusPoint],
    ) -> Feedback:
        row = FeedbackORM(
            session_id=session_id,
            trait_summary_raw=json.dumps([t.model_dump() for t in trait_summary]),
            focus_points_raw=json.dumps([f.model_dump() for f in focus_points]),
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError as e:
            self._db.rollback()
            # Same race case as ObservationRepository.create — two
            # concurrent callers both finding no Feedback and both
            # attempting to create one. Translated to a domain
            # sentinel rather than a raw SQLAlchemy exception.
            raise ConflictError(
                f"Feedback already exists for session_id={session_id}"
            ) from e
        return _to_domain(row)

    def find_by_session_id(self, session_id: str) -> Feedback:
        row = self._db.execute(
            select(FeedbackORM).where(FeedbackORM.session_id == session_id)
        ).scalar_one_or_none()
        if row is None:
            raise FeedbackNotFoundError(f"No feedback yet for session_id={session_id}")
        return _to_domain(row)

    def list_by_session_ids(self, session_ids: list[str]) -> list[Feedback]:
        if not session_ids:
            return []
        rows = (
            self._db.execute(
                select(FeedbackORM).where(FeedbackORM.session_id.in_(session_ids))
            )
            .scalars()
            .all()
        )
        return [_to_domain(row) for row in rows]
