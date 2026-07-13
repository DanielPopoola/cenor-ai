from pydantic import BaseModel

from session.domain import Segment, SegmentArea, Speaker, Turn


class FlatTranscriptTurn(BaseModel):
    """
    One turn in the session-wide, Observer-ready transcript. Never
    persisted — built on the fly from Segment/Turn rows and handed
    straight to ai.run_observer. `turn_number` is renumbered globally
    (1..N across the whole session), not the segment-local number
    stored on Turn, so the Observer's turn_ref citations point at a
    single unambiguous sequence regardless of which segment a turn
    came from.

    `area` is tagged per turn (not part of the Observer prompt draft's
    original shape) so the Observer has an explicit topic-boundary
    signal between segments, rather than relying on inferring a topic
    shift from content alone.
    """

    turn_number: int
    speaker: Speaker
    content: str
    code_snapshot: str | None
    area: SegmentArea


def build_flat_transcript(
    segments: list[Segment], turns_by_segment: dict[str, list[Turn]]
) -> list[FlatTranscriptTurn]:
    """
    Walks segments in segment_order, and within each segment walks its
    turns in their existing order, assigning a single incrementing
    global turn_number across the whole session.
    """
    flat_turns: list[FlatTranscriptTurn] = []
    global_turn_number = 1

    for segment in sorted(segments, key=lambda s: s.segment_order):
        for turn in turns_by_segment.get(segment.id, []):
            flat_turns.append(
                FlatTranscriptTurn(
                    turn_number=global_turn_number,
                    speaker=turn.speaker,
                    content=turn.content,
                    code_snapshot=turn.code_snapshot,
                    area=segment.area,
                )
            )
            global_turn_number += 1

    return flat_turns
