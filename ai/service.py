from openai import AsyncOpenAI

from ai.prompts.interviewer import SYSTEM_PROMPT, build_user_message
from common.retry import retry_transient
from config import Settings
from session.domain import InterviewerTurnResponse


class OpenAICompatibleService:
    def __init__(self, settings: Settings):
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_request_timeout_seconds,
        )
        self._model = settings.llm_model

    @retry_transient(max_attempts=3, exceptions=(TimeoutError, ConnectionError))
    async def structure_cv(self, raw_text: str):
        raise NotImplementedError("CVStructurer prompt lands in Epic 2")

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def structure_github(self, raw_profile_data: dict):
        raise NotImplementedError("GitHubStructurer prompt lands in Epic 2")

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
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
    ) -> InterviewerTurnResponse:
        user_message = build_user_message(
            candidate_context=candidate_context,
            job_context=job_context,
            strictness_mode=strictness_mode,
            segment_area=segment_area,
            editor_available=editor_available,
            current_checklist=current_checklist,
            last_candidate_turn_content=last_candidate_turn_content,
            last_code_snapshot=last_code_snapshot,
        )

        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=InterviewerTurnResponse,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Interviewer response did not match the expected schema")
        return parsed

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
