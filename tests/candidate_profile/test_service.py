from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from candidate_profile.domain import CandidateProfile, CVStructured, GitHubStructured, Skill, WorkExperience
from candidate_profile.errors import CandidateProfileNotFoundError, CVExtractionError
from candidate_profile.service import CandidateProfileService
from config import Settings


class FakeCandidateProfileRepository:
    """In-memory stand-in — matches CandidateProfileRepository's method
    shapes exactly, no DB involved."""

    def __init__(self):
        self._by_user_id: dict[str, CandidateProfile] = {}
        self._next_id = 1

    def find_by_user_id(self, user_id: str) -> CandidateProfile:
        if user_id not in self._by_user_id:
            raise CandidateProfileNotFoundError(user_id)
        return self._by_user_id[user_id]

    def find_by_user_id_or_none(self, user_id: str) -> CandidateProfile | None:
        return self._by_user_id.get(user_id)

    def create(self, user_id: str) -> CandidateProfile:
        profile = CandidateProfile(
            id=f"profile-{self._next_id}",
            user_id=user_id,
            updated_at=datetime.now(timezone.utc),
        )
        self._next_id += 1
        self._by_user_id[user_id] = profile
        return profile

    def update_cv(self, user_id, cv_raw_text, cv_attempted, cv_structured):
        existing = self.find_by_user_id(user_id)
        updated = existing.model_copy(
            update={
                "cv_raw_text": cv_raw_text,
                "cv_attempted": cv_attempted,
                "cv_structured": cv_structured,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._by_user_id[user_id] = updated
        return updated

    def update_github(self, user_id, github_username, github_attempted, github_structured):
        existing = self.find_by_user_id(user_id)
        updated = existing.model_copy(
            update={
                "github_username": github_username,
                "github_attempted": github_attempted,
                "github_structured": github_structured,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._by_user_id[user_id] = updated
        return updated


class FakeAIService:
    """structure_cv and structure_github are exercised in these tests —
    the rest raise if accidentally called, so a wrong wiring fails
    loudly rather than silently returning None."""

    def __init__(
        self,
        cv_result: CVStructured | None = None,
        cv_raises: Exception | None = None,
        github_result=None,
        github_raises: Exception | None = None,
    ):
        self._cv_result = cv_result
        self._cv_raises = cv_raises
        self._github_result = github_result
        self._github_raises = github_raises
        self.received_text: str | None = None
        self.received_github_raw: dict | None = None

    async def structure_cv(self, raw_text: str) -> CVStructured:
        self.received_text = raw_text
        if self._cv_raises is not None:
            raise self._cv_raises
        return self._cv_result

    async def structure_github(self, raw_profile_data: dict):
        self.received_github_raw = raw_profile_data
        if self._github_raises is not None:
            raise self._github_raises
        return self._github_result

    async def run_interviewer_turn(self, *args, **kwargs):
        raise AssertionError("not exercised in these tests")

    async def run_observer(self, *args, **kwargs):
        raise AssertionError("not exercised in these tests")

    async def run_feedback_synthesis(self, *args, **kwargs):
        raise AssertionError("not exercised in these tests")


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test")


@pytest.fixture
def fake_repo() -> FakeCandidateProfileRepository:
    return FakeCandidateProfileRepository()


def _good_cv() -> CVStructured:
    return CVStructured(
        is_valid=True,
        work_experience=[WorkExperience(company="Acme", title="Engineer", start_date="2020")],
        skills=[Skill(name="Python")],
    )


def _make_docx_bytes(text: str) -> bytes:
    import io
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --- get_or_create -----------------------------------------------------


def test_get_or_create_creates_when_absent(settings, fake_repo):
    service = CandidateProfileService(settings, fake_repo, ai_service=None)
    profile = service.get_or_create("user-1")
    assert profile.user_id == "user-1"
    assert profile.cv_status == "pending"


def test_get_or_create_returns_existing_without_duplicating(settings, fake_repo):
    service = CandidateProfileService(settings, fake_repo, ai_service=None)
    first = service.get_or_create("user-1")
    second = service.get_or_create("user-1")
    assert first.id == second.id


# --- upload_cv: extraction failure --------------------------------------


async def test_upload_cv_with_unsupported_file_type_raises_extraction_error(
    settings, fake_repo
):
    ai = FakeAIService(cv_result=_good_cv())
    service = CandidateProfileService(settings, fake_repo, ai)

    with pytest.raises(CVExtractionError):
        await service.upload_cv("user-1", b"not a real file", "resume.txt")

    # extraction failure never reaches the AI service
    assert ai.received_text is None


# --- upload_cv: completeness-bar branches (the real business rule) -----


async def test_upload_cv_with_complete_cv_marks_done(settings, fake_repo):
    ai = FakeAIService(cv_result=_good_cv())
    service = CandidateProfileService(settings, fake_repo, ai)

    docx_bytes = _make_docx_bytes("Experienced engineer, Python, Acme Corp 2020")
    profile = await service.upload_cv("user-1", docx_bytes, "resume.docx")

    assert profile.cv_attempted is True
    assert profile.cv_status == "done"
    assert ai.received_text is not None  # sanitized text was passed through


async def test_upload_cv_with_too_thin_cv_marks_failed_but_stores_reason(
    settings, fake_repo
):
    thin_cv = CVStructured(is_valid=True, skills=[])  # no experience, no skills
    ai = FakeAIService(cv_result=thin_cv)
    service = CandidateProfileService(settings, fake_repo, ai)

    docx_bytes = _make_docx_bytes("just a name, nothing else")
    profile = await service.upload_cv("user-1", docx_bytes, "resume.docx")

    assert profile.cv_attempted is True
    assert profile.cv_status == "failed"
    # the CVStructured itself (with is_valid=True) is still stored —
    # only the derived status treats it as unusable
    assert profile.cv_structured is not None
    assert profile.cv_structured.is_valid is True


async def test_upload_cv_when_llm_says_not_a_cv_marks_failed_with_reason_preserved(
    settings, fake_repo
):
    invalid_cv = CVStructured(is_valid=False, reason="This looks like a grocery list, not a CV")
    ai = FakeAIService(cv_result=invalid_cv)
    service = CandidateProfileService(settings, fake_repo, ai)

    docx_bytes = _make_docx_bytes("eggs, milk, bread")
    profile = await service.upload_cv("user-1", docx_bytes, "resume.docx")

    assert profile.cv_status == "failed"
    assert profile.cv_structured.reason == "This looks like a grocery list, not a CV"


async def test_upload_cv_when_ai_service_raises_marks_attempted_with_no_structured_data(
    settings, fake_repo
):
    ai = FakeAIService(cv_raises=RuntimeError("provider timeout"))
    service = CandidateProfileService(settings, fake_repo, ai)

    docx_bytes = _make_docx_bytes("a real looking cv")
    profile = await service.upload_cv("user-1", docx_bytes, "resume.docx")

    assert profile.cv_attempted is True
    assert profile.cv_status == "failed"
    assert profile.cv_structured is None


async def test_upload_cv_when_ai_service_unavailable_raises_structuring_error(
    settings, fake_repo
):
    from candidate_profile.errors import CVStructuringError

    service = CandidateProfileService(settings, fake_repo, ai_service=None)
    docx_bytes = _make_docx_bytes("a real looking cv")

    with pytest.raises(CVStructuringError):
        await service.upload_cv("user-1", docx_bytes, "resume.docx")


# --- connect_github: the non-blocking business rule ---------------------


_FAKE_RAW_GITHUB_DATA = {
    "profile": {"created_at": "2015-01-01T00:00:00Z"},
    "repos": [{"language": "Python"}, {"language": "Go"}],
}


async def test_connect_github_success_marks_done_and_computes_fields(settings, fake_repo):
    llm_result = GitHubStructured(is_valid=True, bio="Builder")
    ai = FakeAIService(github_result=llm_result)
    service = CandidateProfileService(settings, fake_repo, ai)

    with patch(
        "candidate_profile.service.fetch_github_raw_profile",
        new=AsyncMock(return_value=_FAKE_RAW_GITHUB_DATA),
    ):
        profile = await service.connect_github("user-1", "octocat")

    assert profile.github_attempted is True
    assert profile.github_status == "done"
    assert profile.github_structured.bio == "Builder"
    # computed fields overwrite whatever the LLM returned for them
    assert profile.github_structured.top_languages == ["Python", "Go"]
    assert profile.github_structured.account_age_years is not None


async def test_connect_github_fetch_failure_is_non_blocking(settings, fake_repo):
    """The core business rule: a GitHub failure must never raise —
    profile creation / CV-only flow continues per TDD."""
    from candidate_profile.errors import GitHubFetchError

    ai = FakeAIService()
    service = CandidateProfileService(settings, fake_repo, ai)

    with patch(
        "candidate_profile.service.fetch_github_raw_profile",
        new=AsyncMock(side_effect=GitHubFetchError("user not found")),
    ):
        profile = await service.connect_github("user-1", "no-such-user")

    # no exception raised — this is the point of the test
    assert profile.github_attempted is True
    assert profile.github_structured is None
    assert profile.github_status == "failed"


async def test_connect_github_structuring_failure_is_non_blocking(settings, fake_repo):
    ai = FakeAIService(github_raises=RuntimeError("provider timeout"))
    service = CandidateProfileService(settings, fake_repo, ai)

    with patch(
        "candidate_profile.service.fetch_github_raw_profile",
        new=AsyncMock(return_value=_FAKE_RAW_GITHUB_DATA),
    ):
        profile = await service.connect_github("user-1", "octocat")

    assert profile.github_attempted is True
    assert profile.github_structured is None
    assert profile.github_status == "failed"


async def test_connect_github_when_ai_unavailable_is_non_blocking(settings, fake_repo):
    service = CandidateProfileService(settings, fake_repo, ai_service=None)

    with patch(
        "candidate_profile.service.fetch_github_raw_profile",
        new=AsyncMock(return_value=_FAKE_RAW_GITHUB_DATA),
    ):
        profile = await service.connect_github("user-1", "octocat")

    assert profile.github_attempted is True
    assert profile.github_structured is None


async def test_profile_never_attempted_github_reads_as_skipped_not_failed(settings, fake_repo):
    """Distinguishes 'never tried' from 'tried and failed' — both leave
    github_structured null, but only attempted+failed should read as
    'failed'. See domain.py's github_status."""
    service = CandidateProfileService(settings, fake_repo, ai_service=None)
    profile = service.get_or_create("user-1")
    assert profile.github_status == "skipped"
