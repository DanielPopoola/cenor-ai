from ai.prompts.trait_mapping import build_trait_mapping


def test_coding_lens_includes_execution_integrity():
    mapping = build_trait_mapping("coding")
    assert "execution_integrity" in mapping
    assert mapping["execution_integrity"] == ["code_matches_plan"]


def test_conversational_lens_excludes_execution_integrity():
    mapping = build_trait_mapping("conversational")
    assert "execution_integrity" not in mapping


def test_both_lens_types_include_the_three_base_traits():
    for lens_type in ("coding", "conversational"):
        mapping = build_trait_mapping(lens_type)
        assert set(mapping.keys()) >= {
            "problem_solving", "communication", "clarifies_ambiguity",
        }


def test_problem_solving_maps_to_expected_categories():
    mapping = build_trait_mapping("conversational")
    assert set(mapping["problem_solving"]) == {
        "reasons_through_examples",
        "chooses_approach_intentionally",
        "tests_and_catches_issues",
    }


def test_mutating_returned_mapping_does_not_affect_base_data():
    """build_trait_mapping returns a fresh dict each call — callers
    mutating their copy must not corrupt the module-level constant for
    subsequent calls."""
    mapping = build_trait_mapping("coding")
    mapping["problem_solving"] = []

    fresh = build_trait_mapping("coding")
    assert fresh["problem_solving"] != []
