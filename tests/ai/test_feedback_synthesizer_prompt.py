import json

from ai.prompts.feedback_synthesizer import SYSTEM_PROMPT, build_user_message
from observation.domain import ObservationEntry


def test_system_prompt_mentions_nvc_evaluation_rule():
    assert "Could this sentence be true of the candidate forever" in SYSTEM_PROMPT


def test_system_prompt_includes_resource_honesty_guardrail():
    assert "RESOURCE HONESTY" in SYSTEM_PROMPT
    assert "do NOT invent one" in SYSTEM_PROMPT


def test_system_prompt_allows_up_to_three_focus_points():
    assert "up to 3 focus points" in SYSTEM_PROMPT


def test_build_user_message_includes_trait_mapping():
    message = build_user_message(
        observations=[], trait_mapping={"problem_solving": ["reasons_through_examples"]},
        candidate_profile_summary="",
    )
    payload = json.loads(message)
    assert payload["trait_mapping"] == {"problem_solving": ["reasons_through_examples"]}


def test_build_user_message_serializes_observation_entries():
    entries = [
        ObservationEntry(
            id=1, category="clarifies_ambiguity",
            fact="The candidate asked about input size.", turn_ref=[2],
        )
    ]
    message = build_user_message(
        observations=entries, trait_mapping={}, candidate_profile_summary="",
    )
    payload = json.loads(message)
    assert payload["observer_output"][0]["id"] == 1
    assert payload["observer_output"][0]["category"] == "clarifies_ambiguity"
    assert payload["observer_output"][0]["turn_ref"] == [2]


def test_build_user_message_includes_candidate_profile_summary():
    message = build_user_message(
        observations=[], trait_mapping={}, candidate_profile_summary="Skills: Python, Go",
    )
    payload = json.loads(message)
    assert payload["candidate_profile_summary"] == "Skills: Python, Go"


def test_build_user_message_handles_empty_observations():
    message = build_user_message(observations=[], trait_mapping={}, candidate_profile_summary="")
    payload = json.loads(message)
    assert payload["observer_output"] == []
