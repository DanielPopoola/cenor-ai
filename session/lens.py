from typing import Literal

from session.domain import Segment

LensType = Literal["coding", "conversational"]


def derive_lens_type(segments: list[Segment]) -> LensType:
    return "coding" if any(s.editor_available for s in segments) else "conversational"
