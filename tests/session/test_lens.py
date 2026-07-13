from session.domain import Segment
from session.lens import derive_lens_type


def _segment(area: str, editor_available: bool) -> Segment:
    return Segment(
        id=f"segment-{area}",
        session_id="session-1",
        segment_order=0,
        area=area,  # type: ignore
        editor_available=editor_available,
        duration_limit_minutes=10,
    )


def test_derives_coding_when_any_segment_has_editor():
    segments = [
        _segment("programming_algorithms", editor_available=True),
        _segment("system_design", editor_available=False),
    ]
    assert derive_lens_type(segments) == "coding"


def test_derives_conversational_when_no_segment_has_editor():
    segments = [
        _segment("frameworks_tools", editor_available=False),
        _segment("system_design", editor_available=False),
    ]
    assert derive_lens_type(segments) == "conversational"


def test_empty_segment_list_derives_conversational():
    assert derive_lens_type([]) == "conversational"


def test_single_coding_segment_derives_coding():
    assert derive_lens_type([_segment("programming_algorithms", True)]) == "coding"
