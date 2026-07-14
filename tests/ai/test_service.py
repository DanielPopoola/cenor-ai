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


# --- run_observer -----------------------------------------------------


def _mock_observer_completion(entries):
    from ai.prompts.observer import ObserverResponse

    parsed = ObserverResponse(entries=entries) if entries is not None else None
    completion = MagicMock()
    message = MagicMock()
    message.parsed = parsed
    completion.choices = [MagicMock(message=message)]
    return completion


async def test_run_observer_returns_unwrapped_entries_list(settings):
    """The OpenAI call boundary needs a wrapper object for schema-
    constrained output (ObserverResponse), but callers of run_observer
    should get back a bare list[ObservationEntry] — the wrapper is an
    implementation detail, never leaked outward."""
    from observation.domain import ObservationEntry

    service = OpenAICompatibleService(settings)
    expected_entries = [
        ObservationEntry(
            id=1, category="clarifies_ambiguity",
            fact="The candidate asked about input size.", turn_ref=[2],
        )
    ]

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_observer_completion(expected_entries)),
    ):
        result = await service.run_observer(
            full_transcript=[{"turn_number": 1, "speaker": "interviewer", "content": "Q"}],
            lens_type="coding",
        )

    assert result == expected_entries


async def test_run_observer_raises_when_response_fails_to_parse(settings):
    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_observer_completion(None)),
    ):
        with pytest.raises(ValueError):
            await service.run_observer(full_transcript=[], lens_type="coding")


async def test_run_observer_requests_schema_constrained_output(settings):
    from ai.prompts.observer import ObserverResponse

    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_observer_completion([])),
    ) as mock_parse:
        await service.run_observer(full_transcript=[], lens_type="coding")

    _, kwargs = mock_parse.call_args
    assert kwargs["response_format"] is ObserverResponse


async def test_run_observer_passes_lens_type_into_system_prompt(settings):
    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_observer_completion([])),
    ) as mock_parse:
        await service.run_observer(full_transcript=[], lens_type="conversational")

    _, kwargs = mock_parse.call_args
    system_message = kwargs["messages"][0]["content"]
    assert "does not apply" in system_message  # conversational-lens exclusion note


async def test_run_observer_passes_transcript_in_user_message(settings):
    service = OpenAICompatibleService(settings)
    transcript = [{"turn_number": 1, "speaker": "candidate", "content": "hello", "code_snapshot": None, "area": "system_design"}]

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_observer_completion([])),
    ) as mock_parse:
        await service.run_observer(full_transcript=transcript, lens_type="conversational")

    _, kwargs = mock_parse.call_args
    user_message = kwargs["messages"][1]["content"]
    assert "hello" in user_message


async def test_run_observer_defaults_to_zero_shot_variant(settings):
    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_observer_completion([])),
    ) as mock_parse:
        await service.run_observer(full_transcript=[], lens_type="coding")

    system_message = mock_parse.call_args.kwargs["messages"][0]["content"]
    assert "EXAMPLES (illustrative" not in system_message


async def test_run_observer_uses_few_shot_variant_when_requested(settings):
    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_observer_completion([])),
    ) as mock_parse:
        await service.run_observer(full_transcript=[], lens_type="coding", variant="few_shot")

    system_message = mock_parse.call_args.kwargs["messages"][0]["content"]
    assert "EXAMPLES (illustrative" in system_message


# --- run_feedback_synthesis ---------------------------------------------


def _mock_feedback_completion(result):
    completion = MagicMock()
    message = MagicMock()
    message.parsed = result
    completion.choices = [MagicMock(message=message)]
    return completion


async def test_run_feedback_synthesis_returns_parsed_result(settings):
    from feedback.domain import FeedbackResult, TraitSummary
    from observation.domain import ObservationEntry

    service = OpenAICompatibleService(settings)
    expected = FeedbackResult(
        trait_summary=[
            TraitSummary(trait="problem_solving", summary="did X", source_observations=[1])
        ],
        focus_points=[],
    )

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_feedback_completion(expected)),
    ):
        result = await service.run_feedback_synthesis(
            observations=[
                ObservationEntry(id=1, category="clarifies_ambiguity", fact="asked a question", turn_ref=[1])
            ],
            lens_type="coding",
            trait_mapping={"problem_solving": ["reasons_through_examples"]},
            candidate_profile_summary="",
        )

    assert result == expected


async def test_run_feedback_synthesis_raises_when_response_fails_to_parse(settings):
    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_feedback_completion(None)),
    ):
        with pytest.raises(ValueError):
            await service.run_feedback_synthesis(
                observations=[], lens_type="coding", trait_mapping={}, candidate_profile_summary="",
            )


async def test_run_feedback_synthesis_requests_schema_constrained_output(settings):
    from feedback.domain import FeedbackResult

    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_feedback_completion(FeedbackResult(trait_summary=[], focus_points=[]))),
    ) as mock_parse:
        await service.run_feedback_synthesis(
            observations=[], lens_type="coding", trait_mapping={}, candidate_profile_summary="",
        )

    _, kwargs = mock_parse.call_args
    assert kwargs["response_format"] is FeedbackResult


async def test_run_feedback_synthesis_passes_trait_mapping_and_summary_in_user_message(settings):
    from feedback.domain import FeedbackResult

    service = OpenAICompatibleService(settings)

    with patch.object(
        service._client.chat.completions,
        "parse",
        new=AsyncMock(return_value=_mock_feedback_completion(FeedbackResult(trait_summary=[], focus_points=[]))),
    ) as mock_parse:
        await service.run_feedback_synthesis(
            observations=[],
            lens_type="conversational",
            trait_mapping={"communication": ["communicates_thinking"]},
            candidate_profile_summary="Skills: Python",
        )

    _, kwargs = mock_parse.call_args
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "NVC" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "communication" in messages[1]["content"]
    assert "Python" in messages[1]["content"]
