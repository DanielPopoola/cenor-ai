from openai import AsyncOpenAI

from config import Settings
from common.retry import retry_transient


class OpenAICompatibleService:
    def __init__(self, settings: Settings):
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_request_timeout_seconds,
        )
        self._model = settings.llm_model

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def structure_cv(self, raw_text: str):
        raise NotImplementedError("CVStructurer prompt lands in Epic 2")

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def structure_github(self, raw_profile_data: dict):
        raise NotImplementedError("GitHubStructurer prompt lands in Epic 2")

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def run_interviewer_turn(
        self,
        transcript_so_far: list[dict],
        candidate_context: dict,
        job_context: dict,
        strictness_mode: str,
    ):
        raise NotImplementedError("Interviewer prompt lands in Epic 2")

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def run_observer(self, full_transcript: list[dict], lens_type: str):
        raise NotImplementedError("Observer prompt lands in Epic 3")

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def run_feedback_synthesis(
        self,
        observations: list,
        lens_type: str,
        trait_mapping: dict,
        candidate_profile_summary: str,
    ):
        raise NotImplementedError("Feedback Synthesizer prompt lands in Epic 3")
