"""
One layer of defense against prompt injection, not a guarantee — catches
known, literal phrasings only. Paired with schema-constrained LLM
output (Pydantic-validated JSON) as the second defense layer, per TDD.

Named wrappers per input type (sanitize_cv_text, etc.) exist so an
audit can grep for `sanitize_` and confirm every prompt-building path
in ai/ calls one, rather than trusting every call site remembered to.
"""

import re

from config import Settings

# Known injection patterns: fake role markers, role-hijack phrases,
# instruction-override phrasing. Matches are replaced with [FILTERED],
# not silently dropped, so the LLM sees that something was removed
# rather than a suspiciously clean seam.
_INJECTION_PATTERNS = [
    re.compile(r"(system|assistant|user)\s*:\s*", re.IGNORECASE),
    re.compile(
        r"ignore (all |any )?(previous|prior|above) instructions", re.IGNORECASE
    ),
    re.compile(r"disregard (all |any )?(previous|prior|above)", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"new instructions?:", re.IGNORECASE),
    re.compile(r"</?(system|instructions?)>", re.IGNORECASE),
]


def _sanitize_text(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    for pattern in _INJECTION_PATTERNS:
        normalized = pattern.sub("[FILTERED]", normalized)
    return normalized[:max_chars]


def sanitize_cv_text(text: str, settings: Settings) -> str:
    return _sanitize_text(text, settings.prompt_sanitize_max_chars)


def sanitize_job_description(text: str, settings: Settings) -> str:
    return _sanitize_text(text, settings.prompt_sanitize_max_chars)


def sanitize_candidate_answer(text: str, settings: Settings) -> str:
    return _sanitize_text(text, settings.prompt_sanitize_max_chars)


def sanitize_code_snapshot(text: str, settings: Settings) -> str:
    """
    Code snapshots skip whitespace normalization — collapsing
    indentation/newlines would destroy the thing the Observer is
    actually meant to read. Length cap and pattern filtering still
    apply.
    """
    normalized = text
    for pattern in _INJECTION_PATTERNS:
        normalized = pattern.sub("[FILTERED]", normalized)
    return normalized[: settings.prompt_sanitize_max_chars]
