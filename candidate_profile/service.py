from candidate_profile.domain import CandidateProfile
from candidate_profile.errors import CVStructuringError
from candidate_profile.extraction import extract_cv_text
from candidate_profile.github_computation import (
    compute_account_age_years,
    compute_top_languages,
)
from candidate_profile.github_fetch import fetch_github_raw_profile
from candidate_profile.repository import CandidateProfileRepository
from ai.protocol import AIService
from common.sanitize import sanitize_cv_text
from common.logger import get_logger
from config import Settings

_log = get_logger("candidate_profile.service")


class CandidateProfileService:
    def __init__(
        self,
        settings: Settings,
        repository: CandidateProfileRepository,
        ai_service: AIService | None,
    ):
        self._settings = settings
        self._repository = repository
        self._ai_service = ai_service

    def get_or_create(self, user_id: str) -> CandidateProfile:
        existing = self._repository.find_by_user_id_or_none(user_id)
        if existing is not None:
            return existing
        return self._repository.create(user_id)

    async def upload_cv(
        self, user_id: str, file_bytes: bytes, filename: str
    ) -> CandidateProfile:
        self.get_or_create(user_id)  # ensures a row exists to update

        raw_text = extract_cv_text(file_bytes, filename)
        sanitized = sanitize_cv_text(raw_text, self._settings)

        if self._ai_service is None:
            raise CVStructuringError(
                "AI service is currently unavailable — please try again shortly"
            )

        try:
            structured = await self._ai_service.structure_cv(sanitized)
        except Exception as e:
            _log.error("cv_structuring_failed", user_ref=user_id, error=str(e))
            return self._repository.update_cv(
                user_id=user_id,
                cv_raw_text=sanitized,
                cv_attempted=True,
                cv_structured=None,
            )

        # Stored regardless of usability — even an unusable result (bad
        # is_valid, or too thin per the completeness bar) carries a
        # `reason` worth surfacing to the user. Usability only gates
        # whether a session can be created (see cv_status / TDD), not
        # whether the result is worth keeping.
        return self._repository.update_cv(
            user_id=user_id,
            cv_raw_text=sanitized,
            cv_attempted=True,
            cv_structured=structured,
        )

    async def connect_github(self, user_id: str, username: str) -> CandidateProfile:
        self.get_or_create(user_id)

        try:
            raw_data = await fetch_github_raw_profile(username, self._settings)
        except Exception as e:
            _log.warning("github_fetch_failed", user_ref=user_id, error=str(e))
            return self._repository.update_github(
                user_id=user_id,
                github_username=username,
                github_attempted=True,
                github_structured=None,
            )

        if self._ai_service is None:
            _log.warning("github_structuring_skipped_ai_unavailable", user_ref=user_id)
            return self._repository.update_github(
                user_id=user_id,
                github_username=username,
                github_attempted=True,
                github_structured=None,
            )

        try:
            structured = await self._ai_service.structure_github(raw_data)
        except Exception as e:
            _log.warning("github_structuring_failed", user_ref=user_id, error=str(e))
            return self._repository.update_github(
                user_id=user_id,
                github_username=username,
                github_attempted=True,
                github_structured=None,
            )

        # top_languages / account_age_years are computed here, not
        # trusted from the LLM's output — overwritten regardless of
        # what structure_github returned for those fields, per TDD.
        completed = structured.model_copy(
            update={
                "account_age_years": compute_account_age_years(raw_data["profile"]),
                "top_languages": compute_top_languages(raw_data["repos"]),
            }
        )

        return self._repository.update_github(
            user_id=user_id,
            github_username=username,
            github_attempted=True,
            github_structured=completed,
        )
