import json

from ai.prompts.observer import build_system_prompt, build_user_message


def test_coding_lens_includes_code_matches_plan_category():
    prompt = build_system_prompt(lens_type="coding")
    assert "code_matches_plan" in prompt
    assert "This category requires you to look at BOTH" in prompt


def test_conversational_lens_excludes_code_matches_plan_instructions():
    prompt = build_system_prompt(lens_type="conversational")
    assert "This category requires you to look at BOTH" not in prompt
    assert "does not apply" in prompt


def test_conversational_lens_still_mentions_category_by_name_in_the_exclusion_note():
    """The note explaining category 6 doesn't apply must still name it,
    so the model knows exactly what it's being told to skip."""
    prompt = build_system_prompt(lens_type="conversational")
    assert "code_matches_plan" in prompt


def test_zero_shot_variant_excludes_examples_block():
    prompt = build_system_prompt(lens_type="coding", variant="zero_shot")
    assert "EXAMPLES (illustrative" not in prompt


def test_few_shot_variant_includes_examples_block():
    prompt = build_system_prompt(lens_type="coding", variant="few_shot")
    assert "EXAMPLES (illustrative" in prompt
    assert "communicates_thinking" in prompt
    assert "code_matches_plan" in prompt


def test_default_variant_is_zero_shot():
    default_prompt = build_system_prompt(lens_type="coding")
    explicit_prompt = build_system_prompt(lens_type="coding", variant="zero_shot")
    assert default_prompt == explicit_prompt


def test_prompt_always_mentions_core_nvc_rule():
    """Both variants and both lens types must carry the core
    fact-vs-judgment instruction — this must never be conditionally
    dropped."""
    for lens_type in ("coding", "conversational"):
        for variant in ("zero_shot", "few_shot"):
            prompt = build_system_prompt(lens_type=lens_type, variant=variant)
            assert "don't mix the two" in prompt
            assert "ZERO ENTRIES IS A VALID, EXPECTED OUTCOME" in prompt


def test_build_user_message_serializes_transcript_as_json():
    transcript = [
        {"turn_number": 1, "speaker": "interviewer", "content": "Q1", "code_snapshot": None, "area": "programming_algorithms"},
        {"turn_number": 2, "speaker": "candidate", "content": "A1", "code_snapshot": None, "area": "programming_algorithms"},
    ]
    message = build_user_message(transcript)
    payload = json.loads(message)
    assert payload["transcript"] == transcript


def test_build_user_message_handles_empty_transcript():
    message = build_user_message([])
    payload = json.loads(message)
    assert payload["transcript"] == []
