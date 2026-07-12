STRICTNESS_RUBRIC: dict[str, dict[str, str]] = {
    "clarifies_ambiguity": {
        "lenient": "Candidate asks any question before proceeding, even a narrow one.",
        "standard": "Candidate asks a question that meaningfully narrows the problem's scope or constraints, not just a surface-level check.",
        "strict": "Candidate proactively identifies a genuine ambiguity or edge case the prompt didn't spell out, and asks about it before it would have caused a wrong turn.",
    },
    "reasons_through_examples": {
        "lenient": "Candidate states an intent to check with an example, even without following through.",
        "standard": "Candidate states an intent to use an example AND provides at least one supporting concrete detail (an input, a value, a scenario).",
        "strict": "Candidate actually traces through a concrete example step by step, showing the reasoning play out, not just naming that they would.",
    },
    "chooses_approach_intentionally": {
        "lenient": "Candidate names an approach, even without justification.",
        "standard": "Candidate names an approach and gives at least one reason for choosing it.",
        "strict": "Candidate names an approach, gives a reason, AND names at least one tradeoff or alternative they considered and rejected.",
    },
    "tests_and_catches_issues": {
        "lenient": "Candidate mentions checking their work in any form, even a vague gesture toward it.",
        "standard": "Candidate identifies a specific edge case or verification step and applies it (in words or code).",
        "strict": "Candidate identifies and applies a specific edge case AND self-corrects something as a direct result of that check.",
    },
    "communicates_thinking": {
        "lenient": "Candidate says something about their reasoning at any point, even a short aside.",
        "standard": "Candidate narrates reasoning before or during the relevant action, not only as a summary after the fact.",
        "strict": "Candidate consistently narrates reasoning throughout the turn — the interviewer could follow the thought process step by step without needing to ask 'why' afterward.",
    },
}
