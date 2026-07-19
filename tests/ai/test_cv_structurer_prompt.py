from ai.prompts.cv_structurer import SYSTEM_PROMPT, build_user_message


def test_build_user_message_includes_raw_cv_text():
    msg = build_user_message("Ada Lovelace, Software Engineer at Acme")
    assert "Ada Lovelace, Software Engineer at Acme" in msg


def test_build_user_message_labels_the_text():
    msg = build_user_message("some cv content")
    assert "CV TEXT" in msg


def test_system_prompt_instructs_best_effort_partial_structuring():
    """Per the design decision: a garbled/sparse CV should still be
    structured as far as possible, not rejected outright."""
    assert "best-effort" in SYSTEM_PROMPT.lower() or "Best-effort" in SYSTEM_PROMPT


def test_system_prompt_reserves_is_valid_false_for_unusable_input():
    assert "is_valid should be false ONLY when" in SYSTEM_PROMPT


def test_system_prompt_forbids_fabrication():
    assert "Do not fabricate" in SYSTEM_PROMPT


def test_system_prompt_documents_all_schema_fields():
    for field in [
        "work_experience",
        "projects",
        "education",
        "certifications",
        "skills",
    ]:
        assert field in SYSTEM_PROMPT
