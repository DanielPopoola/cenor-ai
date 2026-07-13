from datetime import timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from common.errors import ConflictError
from observation.domain import Observation, ObservationEntry
from observation.errors import ObservationNotFoundError
from observation.models import ObservationORM


def _as_utc(created_at):
    if created_at.tzinfo is not None:
        return created_at
    return created_at.replace(tzinfo=timezone.utc)


def _to_domain(row: ObservationORM) -> Observation:
    import json

    raw_entries = json.loads(row.observations_raw)
    return Observation(
        id=row.id,
        session_id=row.session_id,
        entries=[ObservationEntry.model_validate(e) for e in raw_entries],
        created_at=_as_utc(row.created_at),
    )


class ObservationRepository:
    def __init__(self, db: DBSession):
        self._db = db

    def create(self, session_id: str, entries: list[ObservationEntry]) -> Observation:
        import json

        row = ObservationORM(
            session_id=session_id,
            observations_raw=json.dumps([e.model_dump() for e in entries]),
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError as e:
            self._db.rollback()
            # Hit when two concurrent callers both find no Observation
            # and both attempt to create one — e.g. two overlapping
            # GET /observations self-healing retries, or the
            # background task racing a self-healing retry. Translated
            # into a domain-meaningful sentinel rather than leaking a
            # raw SQLAlchemy exception; callers can catch this and
            # re-fetch the (now-existing) row instead of crashing.
            raise ConflictError(
                f"An observation already exists for session_id={session_id}"
            ) from e
        return _to_domain(row)

    def find_by_session_id(self, session_id: str) -> Observation:
        row = self._db.execute(
            select(ObservationORM).where(ObservationORM.session_id == session_id)
        ).scalar_one_or_none()
        if row is None:
            raise ObservationNotFoundError(
                f"No observation yet for session_id={session_id}"
            )
        return _to_domain(row)
