from datetime import datetime
from typing import Literal

from pydantic import BaseModel


ObservationCategory = Literal[
    "clarifies_ambiguity",
    "reasons_through_examples",
    "chooses_approach_intentionally",
    "tests_and_catches_issues",
    "communicates_thinking",
    "code_matches_plan",
]


class ObservationEntry(BaseModel):
    id: int
    category: ObservationCategory
    fact: str
    turn_ref: list[int]


class Observation(BaseModel):
    id: str
    session_id: str
    entries: list[ObservationEntry]
    created_at: datetime
