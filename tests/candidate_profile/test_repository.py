import pytest

from auth.models import UserORM
from candidate_profile.domain import CVStructured, GitHubStructured, Skill, WorkExperience
from candidate_profile.errors import CandidateProfileNotFoundError
from candidate_profile.repository import CandidateProfileRepository


@pytest.fixture
def user_id(db_session) -> str:
    """A real users row — candidate_profiles.user_id is a hard FK."""
    row = UserORM(email="cp-repo@example.com", name="CP Repo", google_sub="cp-repo-sub")
    db_session.add(row)
    db_session.flush()
    return row.id


def test_create_and_find_by_user_id(db_session, user_id):
    repo = CandidateProfileRepository(db_session)
    created = repo.create(user_id)

    found = repo.find_by_user_id(user_id)
    assert found.id == created.id
    assert found.user_id == user_id
    assert found.cv_structured is None
    assert found.cv_attempted is False


def test_find_by_user_id_not_found_raises_sentinel(db_session):
    repo = CandidateProfileRepository(db_session)
    with pytest.raises(CandidateProfileNotFoundError):
        repo.find_by_user_id("no-such-user")


def test_find_by_user_id_or_none_returns_none_when_absent(db_session):
    """Expected-empty case: absence is a valid branch, not an error."""
    repo = CandidateProfileRepository(db_session)
    assert repo.find_by_user_id_or_none("no-such-user") is None


def test_find_by_user_id_or_none_returns_profile_when_present(db_session, user_id):
    repo = CandidateProfileRepository(db_session)
    created = repo.create(user_id)

    found = repo.find_by_user_id_or_none(user_id)
    assert found is not None
    assert found.id == created.id


def test_update_cv_persists_and_round_trips_structured_data(db_session, user_id):
    repo = CandidateProfileRepository(db_session)
    repo.create(user_id)

    structured = CVStructured(
        is_valid=True,
        name="Ada Lovelace",
        work_experience=[
            WorkExperience(company="Analytical Engines Inc", title="Engineer", start_date="1840")
        ],
        skills=[Skill(name="Python", category="language")],
    )
    updated = repo.update_cv(
        user_id=user_id,
        cv_raw_text="raw cv text",
        cv_attempted=True,
        cv_structured=structured,
    )

    assert updated.cv_raw_text == "raw cv text"
    assert updated.cv_attempted is True
    assert updated.cv_structured is not None
    assert updated.cv_structured.name == "Ada Lovelace"
    assert updated.cv_structured.work_experience[0].company == "Analytical Engines Inc"

    # round-trip via a fresh read, not just the returned object
    reread = repo.find_by_user_id(user_id)
    assert reread.cv_structured.skills[0].name == "Python"


def test_update_cv_with_none_structured_persists_attempted_flag(db_session, user_id):
    """Structuring can fail (LLM error, or unusable result) while the
    attempt itself still needs to be recorded — see service.py."""
    repo = CandidateProfileRepository(db_session)
    repo.create(user_id)

    updated = repo.update_cv(
        user_id=user_id, cv_raw_text="raw text", cv_attempted=True, cv_structured=None
    )
    assert updated.cv_attempted is True
    assert updated.cv_structured is None


def test_update_cv_on_missing_profile_raises_sentinel(db_session, user_id):
    repo = CandidateProfileRepository(db_session)
    with pytest.raises(CandidateProfileNotFoundError):
        repo.update_cv(
            user_id=user_id, cv_raw_text="x", cv_attempted=True, cv_structured=None
        )


def test_update_github_persists_and_round_trips(db_session, user_id):
    repo = CandidateProfileRepository(db_session)
    repo.create(user_id)

    structured = GitHubStructured(is_valid=True, bio="Builder of things", top_languages=["Python", "Go"])
    updated = repo.update_github(
        user_id=user_id,
        github_username="adalovelace",
        github_attempted=True,
        github_structured=structured,
    )

    assert updated.github_username == "adalovelace"
    assert updated.github_structured.bio == "Builder of things"

    reread = repo.find_by_user_id(user_id)
    assert reread.github_structured.top_languages == ["Python", "Go"]


def test_second_profile_for_same_user_violates_unique_constraint(db_session, user_id):
    """The unique=True constraint on user_id enforces the 1:1
    relationship at the DB level, not just by convention."""
    from sqlalchemy.exc import IntegrityError

    repo = CandidateProfileRepository(db_session)
    repo.create(user_id)

    with pytest.raises(IntegrityError):
        repo.create(user_id)
