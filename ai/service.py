from openai import AsyncOpenAI

from ai.prompts.cv_structurer import SYSTEM_PROMPT as CV_STRUCTURER_SYSTEM_PROMPT
from ai.prompts.cv_structurer import build_user_message as build_cv_user_message
from ai.prompts.feedback_synthesizer import SYSTEM_PROMPT as FEEDBACK_SYSTEM_PROMPT
from ai.prompts.feedback_synthesizer import (
    build_user_message as build_feedback_user_message,
)
from ai.prompts.github_structurer import (
    SYSTEM_PROMPT as GITHUB_STRUCTURER_SYSTEM_PROMPT,
)
from ai.prompts.github_structurer import (
    build_user_message as build_github_user_message,
)
from ai.prompts.interviewer import SYSTEM_PROMPT, build_user_message
from ai.prompts.observer import (
    ObserverResponse,
    ObserverVariant,
    build_system_prompt as build_observer_system_prompt,
    build_user_message as build_observer_user_message,
)
from candidate_profile.domain import CVStructured, GitHubStructured
from common.retry import retry_transient
from config import Settings
from feedback.domain import FeedbackResult
from observation.domain import ObservationEntry
from session.domain import InterviewerTurnResponse


class OpenAICompatibleService:
    def __init__(self, settings: Settings):
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_request_timeout_seconds,
        )
        self._model = settings.llm_model
        self._completion_kwargs = (
            {"max_completion_tokens": settings.llm_max_completion_tokens}
            if settings.llm_max_completion_tokens is not None
            else {}
        )

    @retry_transient(max_attempts=3, exceptions=(TimeoutError, ConnectionError))
    async def structure_cv(self, raw_text: str) -> CVStructured:
        user_message = build_cv_user_message(raw_text)

        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": CV_STRUCTURER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=CVStructured,
            **self._completion_kwargs,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError(
                "CV structuring response did not match the expected schema"
            )
        return parsed

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def structure_github(self, raw_profile_data: dict) -> GitHubStructured:
        user_message = build_github_user_message(raw_profile_data)

        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": GITHUB_STRUCTURER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=GitHubStructured,
            **self._completion_kwargs,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError(
                "GitHub structuring response did not match the expected schema"
            )
        return parsed

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
            **self._completion_kwargs,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Interviewer response did not match the expected schema")
        return parsed

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def run_observer(
        self,
        full_transcript: list[dict],
        lens_type: str,
        variant: ObserverVariant = "zero_shot",
    ) -> list[ObservationEntry]:
        system_prompt = build_observer_system_prompt(
            lens_type=lens_type, variant=variant
        )
        user_message = build_observer_user_message(full_transcript)

        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format=ObserverResponse,
            **self._completion_kwargs,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Observer response did not match the expected schema")
        return parsed.entries

    @retry_transient(max_attempts=2, exceptions=(TimeoutError, ConnectionError))
    async def run_feedback_synthesis(
        self,
        observations: list[ObservationEntry],
        lens_type: str,
        trait_mapping: dict,
        candidate_profile_summary: str,
    ) -> FeedbackResult:
        user_message = build_feedback_user_message(
            observations=observations,
            trait_mapping=trait_mapping,
            candidate_profile_summary=candidate_profile_summary,
        )

        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": FEEDBACK_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=FeedbackResult,
            **self._completion_kwargs,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError(
                "Feedback Synthesizer response did not match the expected schema"
            )
        return parsed
