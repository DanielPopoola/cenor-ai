"""
Human-readable labels for session/segment domain enums. Kept out of
session/domain.py itself — display strings are a presentation concern,
not a business-rule concern, and belong in the template-rendering path
(web/templating.py registers these as Jinja filters), not the domain
model.
"""

_AREA_LABELS: dict[str, str] = {
    "programming_algorithms": "Programming & Algorithms",
    "frameworks_tools": "Frameworks & Tools",
    "specialized": "Specialized Skills",
    "system_design": "System Design & Architecture",
}

_SESSION_STATUS_LABELS: dict[str, str] = {
    "in_progress": "In Progress",
    "completed": "Completed",
    "abandoned": "Abandoned",
}


def area_label(area: str) -> str:
    """Falls back to a title-cased version of the raw value rather than
    raising, so an unmapped future SegmentArea doesn't break rendering."""
    return _AREA_LABELS.get(area, area.replace("_", " ").title())


def session_status_label(status: str) -> str:
    return _SESSION_STATUS_LABELS.get(status, status.replace("_", " ").title())
