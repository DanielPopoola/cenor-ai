from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.service import OpenAICompatibleService
from config import Settings
from session.domain import InterviewerTurnResponse, SegmentChecklist


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", llm_api_key="fake-key")


def _mock_completion(parsed: InterviewerTurnResponse | None):
    completion = MagicMock()
    message = MagicMock()
    message.parsed = parsed
    completion.choices = [MagicMock(message=message)]
    return completion


async def test_run_interviewer_turn_returns_parsed_response(settings):
    service = OpenAICompatibleService(settings)
    expected = InterviewerTurnResponse(
        next_question="What would you clarify first?",
        updated_checklist=SegmentChecklist(),
        segment_complete=False,
        reasoning="No evidence yet, opening the segment.",
    )

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_completion(expected)),
    ) as mock_parse:
        result = await service.run_interviewer_turn(
            candidate_context={"name": "Ada"},
            job_context={"title": "Backend Engineer"},
            strictness_mode="standard",
            segment_area="programming_algorithms",
            editor_available=True,
            current_checklist={},
            last_candidate_turn_content=None,
            last_code_snapshot=None,
        )

    assert result.next_question == "What would you clarify first?"
    assert result.segment_complete is False
    # verify schema-constrained output was actually requested
    _, kwargs = mock_parse.call_args
    assert kwargs["response_format"] is InterviewerTurnResponse


async def test_run_interviewer_turn_raises_when_response_fails_to_parse(settings):
    """A malformed/unparseable LLM response must not silently pass
    through as None — schema-constrained output is a security boundary
    (TDD), so a parse failure has to be a loud error."""
    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_completion(None)),
    ):
        with pytest.raises(ValueError):
            await service.run_interviewer_turn(
                candidate_context={},
                job_context={},
                strictness_mode="standard",
                segment_area="programming_algorithms",
                editor_available=True,
                current_checklist={},
                last_candidate_turn_content=None,
                last_code_snapshot=None,
            )


async def test_run_interviewer_turn_passes_system_and_user_messages(settings):
    service = OpenAICompatibleService(settings)
    expected = InterviewerTurnResponse(
        next_question="q",
        updated_checklist=SegmentChecklist(),
        segment_complete=False,
        reasoning="r",
    )

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_completion(expected)),
    ) as mock_parse:
        await service.run_interviewer_turn(
            candidate_context={"name": "Ada"},
            job_context={},
            strictness_mode="lenient",
            segment_area="system_design",
            editor_available=False,
            current_checklist={},
            last_candidate_turn_content="an answer",
            last_code_snapshot=None,
        )

    _, kwargs = mock_parse.call_args
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "Interviewer in Cerno" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "Ada" in messages[1]["content"]
    assert "lenient" in messages[1]["content"]
