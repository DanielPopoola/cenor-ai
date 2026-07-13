from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

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
    """
    Write-once: no update method exists. An Observation is produced a
    single time by the background Observer task and never mutated
    afterward (TDD: Observer runs once, post-session). Tenant
    isolation is NOT enforced here directly — Observation has no
    user_id column of its own; callers are expected to have already
    verified session ownership via SessionRepository.find_session(
    user_id, session_id) before reaching this repository, same pattern
    as session/repository.py's Segment lookups.
    """

    def __init__(self, db: DBSession):
        self._db = db

    def create(self, session_id: str, entries: list[ObservationEntry]) -> Observation:
        import json

        row = ObservationORM(
            session_id=session_id,
            observations_raw=json.dumps([e.model_dump() for e in entries]),
        )
        self._db.add(row)
        self._db.flush()
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
