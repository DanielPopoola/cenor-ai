from candidate_profile.completeness import cv_meets_completeness_bar
from candidate_profile.domain import CVStructured, Project, Skill, WorkExperience


def test_invalid_cv_never_meets_bar_regardless_of_content():
    cv = CVStructured(
        is_valid=False,
        work_experience=[WorkExperience(company="X", title="Y", start_date="2020")],
        skills=[Skill(name="Python")],
    )
    assert cv_meets_completeness_bar(cv) is False


def test_valid_cv_with_no_experience_and_no_skills_fails_bar():
    cv = CVStructured(is_valid=True)
    assert cv_meets_completeness_bar(cv) is False


def test_valid_cv_with_skills_but_no_experience_or_projects_fails_bar():
    cv = CVStructured(is_valid=True, skills=[Skill(name="Python")])
    assert cv_meets_completeness_bar(cv) is False


def test_valid_cv_with_experience_but_no_skills_fails_bar():
    cv = CVStructured(
        is_valid=True,
        work_experience=[WorkExperience(company="X", title="Y", start_date="2020")],
    )
    assert cv_meets_completeness_bar(cv) is False


def test_valid_cv_with_work_experience_and_skills_meets_bar():
    cv = CVStructured(
        is_valid=True,
        work_experience=[WorkExperience(company="X", title="Y", start_date="2020")],
        skills=[Skill(name="Python")],
    )
    assert cv_meets_completeness_bar(cv) is True


def test_valid_cv_with_project_instead_of_work_experience_meets_bar():
    """Projects count the same as work experience — PRD's target user
    (portfolio-strong builders) often has stronger signal in side
    projects than employer history."""
    cv = CVStructured(
        is_valid=True,
        projects=[Project(name="Side project")],
        skills=[Skill(name="Go")],
    )
    assert cv_meets_completeness_bar(cv) is True
