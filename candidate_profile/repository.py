from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from candidate_profile.domain import CandidateProfile, CVStructured, GitHubStructured
from candidate_profile.errors import CandidateProfileNotFoundError
from candidate_profile.models import CandidateProfileORM


def _to_domain(row: CandidateProfileORM) -> CandidateProfile:
    return CandidateProfile(
        id=row.id,
        user_id=row.user_id,
        cv_raw_text=row.cv_raw_text,
        cv_attempted=row.cv_attempted,
        cv_structured=(
            CVStructured.model_validate_json(row.cv_structured)
            if row.cv_structured is not None
            else None
        ),
        github_username=row.github_username,
        github_attempted=row.github_attempted,
        github_structured=(
            GitHubStructured.model_validate_json(row.github_structured)
            if row.github_structured is not None
            else None
        ),
        updated_at=(
            row.updated_at.replace(tzinfo=timezone.utc)
            if row.updated_at.tzinfo is None
            else row.updated_at
        ),
    )


class CandidateProfileRepository:
    def __init__(self, db: DBSession):
        self._db = db

    def find_by_user_id(self, user_id: str) -> CandidateProfile:
        row = self._db.execute(
            select(CandidateProfileORM).where(CandidateProfileORM.user_id == user_id)
        ).scalar_one_or_none()
        if row is None:
            raise CandidateProfileNotFoundError(
                f"No candidate profile for user_id={user_id}"
            )
        return _to_domain(row)

    def find_by_user_id_or_none(self, user_id: str) -> CandidateProfile | None:
        # Expected-empty: callers use this to branch "has this user
        # started onboarding yet" — not a failure to propagate.
        row = self._db.execute(
            select(CandidateProfileORM).where(CandidateProfileORM.user_id == user_id)
        ).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    def create(self, user_id: str) -> CandidateProfile:
        row = CandidateProfileORM(user_id=user_id)
        self._db.add(row)
        self._db.flush()
        return _to_domain(row)

    def update_cv(
        self,
        user_id: str,
        cv_raw_text: str | None,
        cv_attempted: bool,
        cv_structured: CVStructured | None,
    ) -> CandidateProfile:
        row = self._get_row(user_id)
        row.cv_raw_text = cv_raw_text
        row.cv_attempted = cv_attempted
        row.cv_structured = (
            cv_structured.model_dump_json() if cv_structured is not None else None
        )
        self._db.flush()
        return _to_domain(row)

    def update_github(
        self,
        user_id: str,
        github_username: str | None,
        github_attempted: bool,
        github_structured: GitHubStructured | None,
    ) -> CandidateProfile:
        row = self._get_row(user_id)
        row.github_username = github_username
        row.github_attempted = github_attempted
        row.github_structured = (
            github_structured.model_dump_json()
            if github_structured is not None
            else None
        )
        self._db.flush()
        return _to_domain(row)

    def _get_row(self, user_id: str) -> CandidateProfileORM:
        row = self._db.execute(
            select(CandidateProfileORM).where(CandidateProfileORM.user_id == user_id)
        ).scalar_one_or_none()
        if row is None:
            raise CandidateProfileNotFoundError(
                f"No candidate profile for user_id={user_id}"
            )
        return row
