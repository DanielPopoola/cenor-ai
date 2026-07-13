from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from feedback.domain import FeedbackResult
    from observation.domain import ObservationEntry

    from candidate_profile.domain import CVStructured, GitHubStructured
    from session.domain import InterviewerTurnResponse


class AIService(Protocol):
    async def structure_cv(self, raw_text: str) -> "CVStructured":
        """Structures extracted CV text into the CVStructured schema."""
        ...

    async def structure_github(self, raw_profile_data: dict) -> "GitHubStructured":
        """Structures fetched GitHub API data, picking notable repos."""
        ...

    async def run_interviewer_turn(
        self,
        candidate_context: dict,
        job_context: dict,
        strictness_mode: str,
        segment_area: str,
        editor_available: bool,
        current_checklist: dict,
        last_candidate_turn_content: str | None,
        last_code_snapshot: str | None,
    ) -> "InterviewerTurnResponse":
        """
        Runs one Interviewer turn: next question + updated checklist.
        """
        ...

    async def run_observer(
        self, full_transcript: list[dict], lens_type: str, variant: str = "zero_shot"
    ) -> list["ObservationEntry"]:
        """Single-pass observation over a completed session transcript."""
        ...

    async def run_feedback_synthesis(
        self,
        observations: list["ObservationEntry"],
        lens_type: str,
        trait_mapping: dict,
        candidate_profile_summary: str,
    ) -> "FeedbackResult":
        """Groups Observer output into trait summaries + focus points."""
        ...
