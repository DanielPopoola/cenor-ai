import pytest

from auth.errors import UserNotFoundError
from auth.repository import UserRepository
from common.errors import ConflictError


def test_create_and_find_by_id(db_session):
    repo = UserRepository(db_session)
    user = repo.create(email="a@example.com", name="Alice", google_sub="sub-1")

    found = repo.find_by_id(user.id)
    assert found.id == user.id
    assert found.email == "a@example.com"
    assert found.name == "Alice"
    assert found.google_sub == "sub-1"


def test_find_by_id_not_found_raises_sentinel(db_session):
    repo = UserRepository(db_session)
    with pytest.raises(UserNotFoundError):
        repo.find_by_id("does-not-exist")


def test_find_by_google_sub_returns_none_when_absent(db_session):
    """Expected-empty case: absence is a valid branch, not an error."""
    repo = UserRepository(db_session)
    result = repo.find_by_google_sub("no-such-sub")
    assert result is None


def test_find_by_google_sub_returns_user_when_present(db_session):
    repo = UserRepository(db_session)
    created = repo.create(email="b@example.com", name="Bob", google_sub="sub-2")

    found = repo.find_by_google_sub("sub-2")
    assert found is not None
    assert found.id == created.id


def test_create_duplicate_email_raises_conflict(db_session):
    repo = UserRepository(db_session)
    repo.create(email="dup@example.com", name="First", google_sub="sub-a")

    with pytest.raises(ConflictError):
        repo.create(email="dup@example.com", name="Second", google_sub="sub-b")


def test_create_duplicate_google_sub_raises_conflict(db_session):
    repo = UserRepository(db_session)
    repo.create(email="unique1@example.com", name="First", google_sub="sub-dup")

    with pytest.raises(ConflictError):
        repo.create(email="unique2@example.com", name="Second", google_sub="sub-dup")


def test_user_with_no_name_is_allowed(db_session):
    """name is nullable — a Google account may not expose a display name."""
    repo = UserRepository(db_session)
    user = repo.create(email="noname@example.com", name=None, google_sub="sub-noname")
    assert user.name is None

    found = repo.find_by_id(user.id)
    assert found.name is None


def test_created_at_is_timezone_aware_after_db_round_trip(db_session):
    """SQLite drops tzinfo on DateTime columns regardless of
    timezone=True — see auth/repository.py's fix."""
    from datetime import datetime, timezone

    repo = UserRepository(db_session)
    user = repo.create(email="tz-check@example.com", name="TZ", google_sub="tz-sub")

    reread = repo.find_by_id(user.id)
    assert reread.created_at.tzinfo is not None
    elapsed = datetime.now(timezone.utc) - reread.created_at
    assert elapsed.total_seconds() >= 0
