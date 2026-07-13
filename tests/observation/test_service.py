from datetime import datetime, timezone

import pytest

from observation.domain import Observation, ObservationEntry
from observation.service import ObservationService
from session.domain import Segment, Turn


class FakeSessionRepository:
    """Matches SessionRepository's method shapes for the two methods
    ObservationService actually calls — segments/turns are seeded
    directly by the test, no session/segment creation logic needed."""

    def __init__(self, segments: list[Segment], turns_by_segment: dict[str, list[Turn]]):
        self._segments = segments
        self._turns_by_segment = turns_by_segment

    def list_segments_for_session(self, session_id):
        return [s for s in self._segments if s.session_id == session_id]

    def list_turns_for_segment(self, segment_id):
        return self._turns_by_segment.get(segment_id, [])


class FakeObservationRepository:
    def __init__(self):
        self.created_with: dict | None = None
        self._next_id = 1

    def create(self, session_id, entries):
        self.created_with = {"session_id": session_id, "entries": entries}
        obs = Observation(
            id=f"obs-{self._next_id}",
            session_id=session_id,
            entries=entries,
            created_at=datetime.now(timezone.utc),
        )
        self._next_id += 1
        return obs

    def find_by_session_id(self, session_id):
        raise AssertionError("not exercised in these tests")


class FakeAIService:
    def __init__(self, observer_result: list[ObservationEntry] | None = None):
        self._observer_result = observer_result or []
        self.received_transcript: list[dict] | None = None
        self.received_lens_type: str | None = None

    async def run_observer(self, full_transcript, lens_type):
        self.received_transcript = full_transcript
        self.received_lens_type = lens_type
        return self._observer_result

    async def structure_cv(self, *a, **k):
        raise AssertionError("not exercised")

    async def structure_github(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_interviewer_turn(self, *a, **k):
        raise AssertionError("not exercised")

    async def run_feedback_synthesis(self, *a, **k):
        raise AssertionError("not exercised")


def _segment(area: str, editor_available: bool, order: int = 0) -> Segment:
    return Segment(
        id=f"segment-{area}",
        session_id="session-1",
        segment_order=order,
        area=area,  # type: ignore
        editor_available=editor_available,
        duration_limit_minutes=10,
    )


def _turn(segment_id: str, turn_number: int, speaker: str, content: str) -> Turn:
    return Turn(
        id=f"turn-{segment_id}-{turn_number}",
        segment_id=segment_id,
        turn_number=turn_number,
        speaker=speaker,  # type: ignore
        content=content,
        created_at=datetime.now(timezone.utc),
    )


def _entry(entry_id: int) -> ObservationEntry:
    return ObservationEntry(
        id=entry_id,
        category="clarifies_ambiguity",
        fact="The candidate asked a clarifying question.",
        turn_ref=[1],
    )


async def test_run_observation_persists_observer_output():
    seg = _segment("programming_algorithms", editor_available=True)
    turns = {seg.id: [_turn(seg.id, 1, "interviewer", "Q1")]}
    session_repo = FakeSessionRepository([seg], turns)
    obs_repo = FakeObservationRepository()
    ai = FakeAIService(observer_result=[_entry(1)])

    service = ObservationService(session_repo, obs_repo, ai)
    result = await service.run_observation("session-1")

    assert result.session_id == "session-1"
    assert len(result.entries) == 1
    assert obs_repo.created_with["session_id"] == "session-1"


async def test_run_observation_flattens_transcript_before_calling_ai():
    seg0 = _segment("programming_algorithms", editor_available=True, order=0)
    seg1 = _segment("system_design", editor_available=False, order=1)
    turns = {
        seg0.id: [_turn(seg0.id, 1, "interviewer", "coding question")],
        seg1.id: [_turn(seg1.id, 1, "interviewer", "design question")],
    }
    session_repo = FakeSessionRepository([seg0, seg1], turns)
    ai = FakeAIService()

    service = ObservationService(session_repo, FakeObservationRepository(), ai)
    await service.run_observation("session-1")

    assert ai.received_transcript is not None
    assert len(ai.received_transcript) == 2
    # global renumbering happened — both turns present with distinct turn_number
    turn_numbers = [t["turn_number"] for t in ai.received_transcript]
    assert turn_numbers == [1, 2]


async def test_run_observation_derives_coding_lens_when_editor_segment_present():
    seg = _segment("programming_algorithms", editor_available=True)
    session_repo = FakeSessionRepository([seg], {seg.id: [_turn(seg.id, 1, "interviewer", "Q")]})
    ai = FakeAIService()

    service = ObservationService(session_repo, FakeObservationRepository(), ai)
    await service.run_observation("session-1")

    assert ai.received_lens_type == "coding"


async def test_run_observation_derives_conversational_lens_when_no_editor_segment():
    seg = _segment("system_design", editor_available=False)
    session_repo = FakeSessionRepository([seg], {seg.id: [_turn(seg.id, 1, "interviewer", "Q")]})
    ai = FakeAIService()

    service = ObservationService(session_repo, FakeObservationRepository(), ai)
    await service.run_observation("session-1")

    assert ai.received_lens_type == "conversational"


async def test_run_observation_with_zero_entries_is_valid():
    """Zero observations is a valid, expected Observer outcome — must
    not raise, must still persist an (empty) Observation row."""
    seg = _segment("system_design", editor_available=False)
    session_repo = FakeSessionRepository([seg], {seg.id: [_turn(seg.id, 1, "interviewer", "Q")]})
    ai = FakeAIService(observer_result=[])

    service = ObservationService(session_repo, FakeObservationRepository(), ai)
    result = await service.run_observation("session-1")

    assert result.entries == []


async def test_run_observation_raises_when_ai_service_unavailable():
    from common.errors import ValidationError

    seg = _segment("system_design", editor_available=False)
    session_repo = FakeSessionRepository([seg], {})
    service = ObservationService(session_repo, FakeObservationRepository(), ai_service=None)

    with pytest.raises(ValidationError):
        await service.run_observation("session-1")
