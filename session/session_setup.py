from dataclasses import dataclass

from session.domain import SegmentArea

# Order matters: this is the order segments run in during a session.
# Only programming_algorithms gets a code editor — PRD Section 4:
# "Coding is the only area that requires a fundamentally different
# artifact... to properly observe 'does the code match the stated plan'."
_V1_SEGMENT_AREAS: list[tuple[SegmentArea, bool]] = [
    ("programming_algorithms", True),
    ("frameworks_tools", False),
    ("specialized", False),
    ("system_design", False),
]


@dataclass(frozen=True)
class SegmentSpec:
    area: SegmentArea
    editor_available: bool
    duration_limit_minutes: int


def build_default_segments(session_duration_limit_minutes: int) -> list[SegmentSpec]:
    """
    Splits the session's total time roughly evenly across the 4 fixed
    areas. Any remainder minutes (from integer division) are added to
    the last segment rather than dropped, so the segments' durations
    always sum to exactly the session total.
    """
    segment_count = len(_V1_SEGMENT_AREAS)
    base_minutes = session_duration_limit_minutes // segment_count
    remainder = session_duration_limit_minutes - (base_minutes * segment_count)

    specs = []
    for index, (area, editor_available) in enumerate(_V1_SEGMENT_AREAS):
        minutes = base_minutes + (remainder if index == segment_count - 1 else 0)
        specs.append(
            SegmentSpec(
                area=area,
                editor_available=editor_available,
                duration_limit_minutes=minutes,
            )
        )
    return specs
