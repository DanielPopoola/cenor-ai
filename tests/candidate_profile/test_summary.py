from datetime import datetime, timezone

from candidate_profile.domain import (
    CandidateProfile,
    CVStructured,
    GitHubStructured,
    Project,
    Skill,
    WorkExperience,
)
from candidate_profile.summary import summarize_for_feedback


def _profile(**overrides) -> CandidateProfile:
    defaults = dict(
        id="p1", user_id="u1", updated_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return CandidateProfile(**defaults)


def test_returns_empty_string_when_cv_structured_is_none():
    profile = _profile(cv_structured=None)
    assert summarize_for_feedback(profile) == ""


def test_returns_empty_string_when_cv_structured_is_invalid():
    profile = _profile(cv_structured=CVStructured(is_valid=False, reason="not a CV"))
    assert summarize_for_feedback(profile) == ""


def test_includes_current_title_when_present():
    profile = _profile(
        cv_structured=CVStructured(is_valid=True, current_title="Backend Engineer")
    )
    assert "Backend Engineer" in summarize_for_feedback(profile)


def test_includes_skills():
    profile = _profile(
        cv_structured=CVStructured(
            is_valid=True, skills=[Skill(name="Python"), Skill(name="Go")]
        )
    )
    result = summarize_for_feedback(profile)
    assert "Python" in result
    assert "Go" in result


def test_includes_most_recent_work_experience():
    profile = _profile(
        cv_structured=CVStructured(
            is_valid=True,
            work_experience=[
                WorkExperience(company="Acme", title="Engineer", start_date="2022"),
                WorkExperience(company="Old Co", title="Junior Eng", start_date="2018"),
            ],
        )
    )
    result = summarize_for_feedback(profile)
    assert "Acme" in result
    assert "Engineer" in result


def test_includes_up_to_three_project_names():
    profile = _profile(
        cv_structured=CVStructured(
            is_valid=True,
            projects=[Project(name=f"Project {i}") for i in range(5)],
        )
    )
    result = summarize_for_feedback(profile)
    assert "Project 0" in result
    assert "Project 2" in result
    assert "Project 4" not in result


def test_includes_github_languages_when_connected():
    profile = _profile(
        cv_structured=CVStructured(is_valid=True, skills=[Skill(name="Python")]),
        github_structured=GitHubStructured(is_valid=True, top_languages=["Rust", "Go"]),
    )
    result = summarize_for_feedback(profile)
    assert "Rust" in result
    assert "Go" in result


def test_omits_github_section_when_not_connected():
    profile = _profile(
        cv_structured=CVStructured(is_valid=True, skills=[Skill(name="Python")]),
        github_structured=None,
    )
    result = summarize_for_feedback(profile)
    assert "GitHub" not in result


def test_handles_minimal_valid_cv_gracefully():
    """A bare is_valid=True CV with nothing else populated shouldn't
    crash — just produces a thin (possibly empty) summary."""
    profile = _profile(cv_structured=CVStructured(is_valid=True))
    result = summarize_for_feedback(profile)
    assert isinstance(result, str)
