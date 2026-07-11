from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class WorkExperience(BaseModel):
    company: str
    title: str
    location: str | None = None
    start_date: str  # "YYYY-MM" or "YYYY" — string, not a date type; see
    end_date: str | None = None  # TDD note on unreliable LLM date parsing
    description: list[str] = []

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: object) -> object:
        # The model sometimes returns a newline-delimited string instead
        # of a list — normalize here so callers never see the variance.
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        return value


class Project(BaseModel):
    name: str
    description: list[str] = []
    technologies: list[str] = []
    url: str | None = None

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: object) -> object:
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        return value


class Skill(BaseModel):
    name: str
    category: str | None = (
        None  # loose, not an enum — e.g. "language", "infrastructure"
    )


class Education(BaseModel):
    institution: str
    degree: str
    field_of_study: str | None = None
    start_date: str
    end_date: str | None = None


class Certification(BaseModel):
    name: str
    issuing_org: str
    issue_date: str
    expiry_date: str | None = None
    credential_id: str | None = None


class CVStructured(BaseModel):
    is_valid: bool
    reason: str | None = None  # LLM's own account of why, if invalid

    name: str | None = None
    current_title: str | None = None
    summary: str | None = None

    work_experience: list[WorkExperience] = []
    projects: list[Project] = []
    education: list[Education] = []
    certifications: list[Certification] = []
    skills: list[Skill] = []


# --- GitHub structuring schema ------------------------------------------


class NotableRepo(BaseModel):
    name: str
    description: str | None = None
    primary_language: str | None = None
    topics: list[str] = []


class GitHubStructured(BaseModel):
    is_valid: bool
    reason: str | None = None

    bio: str | None = None
    account_age_years: float | None = None  # computed, not LLM-derived
    top_languages: list[str] = []  # computed, not LLM-derived
    notable_repos: list[NotableRepo] = []  # the one LLM-judged field


# --- Top-level profile ----------------------------------------------------


class CandidateProfile(BaseModel):
    id: str
    user_id: str

    cv_raw_text: str | None = None
    cv_attempted: bool = False
    cv_structured: CVStructured | None = None

    github_username: str | None = None
    github_attempted: bool = False
    github_structured: GitHubStructured | None = None

    updated_at: datetime

    @property
    def cv_status(self) -> Literal["done", "pending", "failed"]:
        from candidate_profile.completeness import cv_meets_completeness_bar

        if self.cv_structured is not None and cv_meets_completeness_bar(
            self.cv_structured
        ):
            return "done"
        return "failed" if self.cv_attempted else "pending"

    @property
    def github_status(self) -> Literal["done", "skipped", "failed"]:
        if self.github_structured is not None:
            return "done"
        return "failed" if self.github_attempted else "skipped"
