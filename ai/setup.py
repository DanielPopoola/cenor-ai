"""
create_ai_service() is the one place that decides whether the app can
talk to an LLM provider at all. Classified as an optional dependency at
startup per the TDD — an unreachable provider shouldn't block the app
from booting, since individual requests can fail independently once
traffic arrives. Callers (domain services) must treat a None AIService
as a real, expected branch, not an exceptional case to ignore.
"""

from typing import cast
from ai.service import OpenAICompatibleService
from ai.protocol import AIService
from config import Settings
from common.logger import get_logger

_log = get_logger("ai.setup")


def create_ai_service(settings: Settings) -> AIService | None:
    if not settings.llm_api_key:
        _log.warning("ai_service_not_configured", reason="no llm_api_key set")
        return None

    try:
        return cast(AIService, OpenAICompatibleService(settings))
    except Exception as exc:
        _log.error(
            "ai_service_setup_failed", error_type=type(exc).__name__, message=str(exc)
        )
        return None
