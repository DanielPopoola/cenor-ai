from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from candidate_profile.domain import CandidateProfile, CVStructured, GitHubStructured


class CandidateProfileResponse(BaseModel):
    id: str
    user_id: str
    cv_status: Literal["done", "pending", "failed"]
    cv_structured: CVStructured | None
    github_username: str | None
    github_status: Literal["done", "skipped", "failed"]
    github_structured: GitHubStructured | None
    updated_at: datetime

    @classmethod
    def from_domain(cls, profile: CandidateProfile) -> "CandidateProfileResponse":
        return cls(
            id=profile.id,
            user_id=profile.user_id,
            cv_status=profile.cv_status,
            cv_structured=profile.cv_structured,
            github_username=profile.github_username,
            github_status=profile.github_status,
            github_structured=profile.github_structured,
            updated_at=profile.updated_at,
        )
