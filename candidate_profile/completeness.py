from candidate_profile.domain import CVStructured


def cv_meets_completeness_bar(cv: CVStructured) -> bool:
    if not cv.is_valid:
        return False
    has_experience_signal = bool(cv.work_experience) or bool(cv.projects)
    has_skills = bool(cv.skills)
    return has_experience_signal and has_skills
