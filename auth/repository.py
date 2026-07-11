from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.errors import UserNotFoundError
from auth.models import UserORM
from common.errors import ConflictError


def _to_domain(row: UserORM) -> User:
    return User(
        id=row.id,
        email=row.email,
        name=row.name,
        google_sub=row.google_sub,
        created_at=row.created_at,
    )


class UserRepository:
    def __init__(self, db: DBSession):
        self._db = db

    def find_by_id(self, user_id: str) -> User:
        row = self._db.get(UserORM, user_id)
        if row is None:
            raise UserNotFoundError(f"No user with id={user_id}")
        return _to_domain(row)

    def find_by_google_sub(self, google_sub: str) -> User | None:
        # Expected-empty: caller uses this to branch "does this Google
        # account already have a User row" — not a failure to propagate.
        row = self._db.execute(
            select(UserORM).where(UserORM.google_sub == google_sub)
        ).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    def create(self, email: str, name: str | None, google_sub: str) -> User:
        row = UserORM(email=email, name=name, google_sub=google_sub)
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError as e:
            self._db.rollback()
            raise ConflictError(
                f"A user with email={email} or google_sub={google_sub} already exists"
            ) from e
        return _to_domain(row)
