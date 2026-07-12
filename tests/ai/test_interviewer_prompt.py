import json

from ai.prompts.interviewer import build_user_message
from ai.prompts.strictness_rubric import STRICTNESS_RUBRIC


def test_build_user_message_includes_all_required_context():
    msg = build_user_message(
        candidate_context={"name": "Ada"},
        job_context={"title": "Backend Engineer"},
        strictness_mode="standard",
        segment_area="programming_algorithms",
        editor_available=True,
        current_checklist={"clarifies_ambiguity": "not_yet"},
        last_candidate_turn_content="I'd use a hash map here.",
        last_code_snapshot="def foo(): pass",
    )
    payload = json.loads(msg)
    assert payload["candidate_context"]["name"] == "Ada"
    assert payload["job_context"]["title"] == "Backend Engineer"
    assert payload["segment_area"] == "programming_algorithms"
    assert payload["editor_available"] is True
    assert payload["strictness_mode"] == "standard"
    assert payload["current_checklist"]["clarifies_ambiguity"] == "not_yet"
    assert payload["last_candidate_turn_content"] == "I'd use a hash map here."
    assert payload["last_code_snapshot"] == "def foo(): pass"


def test_build_user_message_never_includes_full_transcript_key():
    """Section 2a: the Interviewer deliberately does not receive the
    full transcript — only checklist + last turn(s)."""
    msg = build_user_message(
        candidate_context={},
        job_context={},
        strictness_mode="standard",
        segment_area="programming_algorithms",
        editor_available=False,
        current_checklist={},
        last_candidate_turn_content=None,
        last_code_snapshot=None,
    )
    payload = json.loads(msg)
    assert "transcript" not in payload
    assert "transcript_so_far" not in payload
    assert "turns" not in payload


def test_build_user_message_flags_segment_opening_when_no_prior_turn():
    msg = build_user_message(
        candidate_context={},
        job_context={},
        strictness_mode="standard",
        segment_area="frameworks_tools",
        editor_available=False,
        current_checklist={},
        last_candidate_turn_content=None,
        last_code_snapshot=None,
    )
    payload = json.loads(msg)
    assert payload["is_segment_opening"] is True


def test_build_user_message_not_opening_when_prior_turn_exists():
    msg = build_user_message(
        candidate_context={},
        job_context={},
        strictness_mode="standard",
        segment_area="frameworks_tools",
        editor_available=False,
        current_checklist={},
        last_candidate_turn_content="Some answer",
        last_code_snapshot=None,
    )
    payload = json.loads(msg)
    assert payload["is_segment_opening"] is False


def test_build_user_message_injects_rubric_matching_the_strictness_mode():
    msg = build_user_message(
        candidate_context={},
        job_context={},
        strictness_mode="strict",
        segment_area="programming_algorithms",
        editor_available=True,
        current_checklist={},
        last_candidate_turn_content=None,
        last_code_snapshot=None,
    )
    payload = json.loads(msg)
    rubric = payload["strictness_rubric_for_this_mode"]
    for behavior, bars in STRICTNESS_RUBRIC.items():
        assert rubric[behavior] == bars["strict"]


def test_strictness_rubric_defines_all_three_modes_for_every_behavior():
    for behavior, bars in STRICTNESS_RUBRIC.items():
        assert set(bars.keys()) == {"lenient", "standard", "strict"}
        for mode, text in bars.items():
            assert isinstance(text, str) and len(text) > 0
