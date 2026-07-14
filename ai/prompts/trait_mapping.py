"""
Trait mapping: which Observer categories feed which Feedback trait.
Passed into the Feedback Synthesizer prompt as data
(feedback_synthesizer_prompt_draft.md: "passed in as data, not
hardcoded into this prompt... swappable in development... without
changing anything below"). Mirrors strictness_rubric.py's shape — a
plain module-level constant, not buried inline in a prompt string.

execution_integrity is deliberately absent from the base mapping —
it's the coding-lens-only trait (fed by code_matches_plan, which the
Observer itself only ever produces for coding-lens sessions per
observer_prompt_draft.md). build_trait_mapping() is the single place
that decides whether to include it, so that conditional isn't
duplicated at every call site — same reasoning as
session/lens.py's derive_lens_type.
"""

_BASE_TRAIT_MAPPING: dict[str, list[str]] = {
    "problem_solving": [
        "reasons_through_examples",
        "chooses_approach_intentionally",
        "tests_and_catches_issues",
    ],
    "communication": ["communicates_thinking"],
    "clarifies_ambiguity": ["clarifies_ambiguity"],
}

_EXECUTION_INTEGRITY_TRAIT: dict[str, list[str]] = {
    "execution_integrity": ["code_matches_plan"],
}


def build_trait_mapping(lens_type: str) -> dict[str, list[str]]:
    """
    Returns the trait mapping for this session's lens_type.
    execution_integrity is only included when lens_type == "coding" —
    matching the Observer's own behavior of only ever producing
    code_matches_plan entries for coding-lens sessions. Including the
    trait for a conversational-lens session would give the Feedback
    Synthesizer a trait key with zero possible backing observations,
    which the prompt's own rule already says to omit — this just
    avoids handing it a trait that could never be satisfied in the
    first place.
    """
    mapping = dict(_BASE_TRAIT_MAPPING)
    if lens_type == "coding":
        mapping.update(_EXECUTION_INTEGRITY_TRAIT)
    return mapping
