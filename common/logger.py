import json
import logging
import sys
from datetime import datetime, timezone

from common.middleware import get_request_id

_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.handlers = [handler]
    for noisy_logger in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    _configured = True


class StructuredLogger:
    def __init__(self, module: str):
        self._module = module
        self._logger = logging.getLogger(module)

    def _emit(self, level: int, event: str, **fields) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "module": self._module,
            "event": event,
            "request_id": get_request_id() or None,
            **fields,
        }
        self._logger.log(level, json.dumps(payload, default=str))

    def info(self, event: str, **fields) -> None:
        self._emit(logging.INFO, event, **fields)

    def warning(self, event: str, **fields) -> None:
        self._emit(logging.WARNING, event, **fields)

    def error(self, event: str, **fields) -> None:
        self._emit(logging.ERROR, event, **fields)


def get_logger(module: str) -> StructuredLogger:
    return StructuredLogger(module)
