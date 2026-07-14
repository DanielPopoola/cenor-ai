from candidate_profile.domain import CandidateProfile


def summarize_for_feedback(profile: CandidateProfile) -> str:
    """
    Condenses a CandidateProfile into a short plain-text summary for
    the Feedback Synthesizer prompt. Per feedback_synthesizer_prompt_draft.md,
    this context is used ONLY to help pick relevant resources for focus
    points (e.g. suggesting a distributed-systems resource to someone
    with backend experience) — it must never influence which traits or
    focus points get generated, which come strictly from the Observer's
    output for this session.

    Returns an empty string if there's nothing usable to summarize
    (e.g. cv_structured somehow missing at this point) rather than
    raising — a missing summary should degrade gracefully, not block
    feedback generation, since it's explicitly a "nice to have" input
    per the prompt draft.
    """
    if profile.cv_structured is None or not profile.cv_structured.is_valid:
        return ""

    cv = profile.cv_structured
    parts: list[str] = []

    if cv.current_title:
        parts.append(f"Current title: {cv.current_title}")

    if cv.skills:
        skill_names = ", ".join(s.name for s in cv.skills)
        parts.append(f"Skills: {skill_names}")

    if cv.work_experience:
        most_recent = cv.work_experience[0]
        parts.append(f"Most recent role: {most_recent.title} at {most_recent.company}")

    if cv.projects:
        project_names = ", ".join(p.name for p in cv.projects[:3])
        parts.append(f"Notable projects: {project_names}")

    if (
        profile.github_structured is not None
        and profile.github_structured.top_languages
    ):
        languages = ", ".join(profile.github_structured.top_languages)
        parts.append(f"Frequently used languages (GitHub): {languages}")

    return " | ".join(parts)
