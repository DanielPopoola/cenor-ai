from datetime import datetime, timezone

from session.domain import Segment, Turn
from session.transcript import build_flat_transcript


def _segment(segment_order: int, area: str, segment_id: str | None = None) -> Segment:
    return Segment(
        id=segment_id or f"segment-{segment_order}",
        session_id="session-1",
        segment_order=segment_order,
        area=area,  # type: ignore
        editor_available=(area == "programming_algorithms"),
        duration_limit_minutes=10,
    )


def _turn(
    segment_id: str,
    turn_number: int,
    speaker: str,
    content: str,
    code_snapshot: str | None = None,
) -> Turn:
    return Turn(
        id=f"turn-{segment_id}-{turn_number}",
        segment_id=segment_id,
        turn_number=turn_number,
        speaker=speaker,  # type: ignore
        content=content,
        code_snapshot=code_snapshot,
        created_at=datetime.now(timezone.utc),
    )


def test_renumbers_turns_globally_across_segments():
    seg0 = _segment(0, "programming_algorithms")
    seg1 = _segment(1, "frameworks_tools")

    turns_by_segment = {
        seg0.id: [
            _turn(seg0.id, 1, "interviewer", "Q1"),
            _turn(seg0.id, 2, "candidate", "A1"),
        ],
        seg1.id: [
            _turn(seg1.id, 1, "interviewer", "Q2"),  # segment-local number restarts at 1
        ],
    }

    flat = build_flat_transcript([seg0, seg1], turns_by_segment)

    assert [t.turn_number for t in flat] == [1, 2, 3]
    assert [t.content for t in flat] == ["Q1", "A1", "Q2"]


def test_orders_by_segment_order_regardless_of_input_list_order():
    seg0 = _segment(0, "programming_algorithms")
    seg1 = _segment(1, "system_design")

    turns_by_segment = {
        seg0.id: [_turn(seg0.id, 1, "interviewer", "first segment question")],
        seg1.id: [_turn(seg1.id, 1, "interviewer", "second segment question")],
    }

    # segments passed in reverse order — function must sort by segment_order itself
    flat = build_flat_transcript([seg1, seg0], turns_by_segment)

    assert [t.content for t in flat] == [
        "first segment question",
        "second segment question",
    ]


def test_tags_each_turn_with_its_segments_area():
    seg0 = _segment(0, "programming_algorithms")
    seg1 = _segment(1, "system_design")

    turns_by_segment = {
        seg0.id: [_turn(seg0.id, 1, "interviewer", "coding question")],
        seg1.id: [_turn(seg1.id, 1, "interviewer", "design question")],
    }

    flat = build_flat_transcript([seg0, seg1], turns_by_segment)

    assert flat[0].area == "programming_algorithms"
    assert flat[1].area == "system_design"


def test_preserves_code_snapshot():
    seg0 = _segment(0, "programming_algorithms")
    turns_by_segment = {
        seg0.id: [_turn(seg0.id, 1, "candidate", "here's my code", code_snapshot="def f(): pass")],
    }

    flat = build_flat_transcript([seg0], turns_by_segment)

    assert flat[0].code_snapshot == "def f(): pass"


def test_turn_without_code_snapshot_stays_none():
    seg0 = _segment(0, "frameworks_tools")
    turns_by_segment = {
        seg0.id: [_turn(seg0.id, 1, "candidate", "verbal answer only")],
    }

    flat = build_flat_transcript([seg0], turns_by_segment)

    assert flat[0].code_snapshot is None


def test_segment_with_no_turns_contributes_nothing():
    seg0 = _segment(0, "programming_algorithms")
    seg1 = _segment(1, "specialized")  # never got any turns, e.g. skipped/abandoned

    turns_by_segment = {
        seg0.id: [_turn(seg0.id, 1, "interviewer", "only real question")],
        # seg1.id intentionally absent from the dict
    }

    flat = build_flat_transcript([seg0, seg1], turns_by_segment)

    assert len(flat) == 1
    assert flat[0].content == "only real question"


def test_empty_session_produces_empty_transcript():
    assert build_flat_transcript([], {}) == []


def test_preserves_within_segment_turn_order():
    seg0 = _segment(0, "programming_algorithms")
    turns_by_segment = {
        seg0.id: [
            _turn(seg0.id, 1, "interviewer", "Q1"),
            _turn(seg0.id, 2, "candidate", "A1"),
            _turn(seg0.id, 3, "interviewer", "Q2"),
            _turn(seg0.id, 4, "candidate", "A2"),
        ],
    }

    flat = build_flat_transcript([seg0], turns_by_segment)

    assert [t.speaker for t in flat] == [
        "interviewer", "candidate", "interviewer", "candidate",
    ]
