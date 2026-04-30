import json
import logging
import sys
import time
from functools import lru_cache
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langfuse import get_client
from langfuse.langchain import CallbackHandler

LOG = logging.getLogger(__name__)

_RESERVED_LOG_KEYS = set(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": int(record.created * 1000),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _RESERVED_LOG_KEYS and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


class ToolCallLogger(AsyncCallbackHandler):
    """Stdout JSON: tool name, latency, outcome. Never logs args/results (PII)."""

    def __init__(self) -> None:
        self._starts: dict[UUID, tuple[str, float]] = {}

    async def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any
    ) -> None:
        name = serialized.get("name", "unknown") if serialized else "unknown"
        self._starts[run_id] = (name, time.monotonic())

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        rec = self._starts.pop(run_id, None)
        if rec is None:
            return
        name, t0 = rec
        LOG.info(
            "tool_call",
            extra={
                "tool": name,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "outcome": "ok",
            },
        )

    async def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        rec = self._starts.pop(run_id, None)
        if rec is None:
            return
        name, t0 = rec
        LOG.info(
            "tool_call",
            extra={
                "tool": name,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "outcome": "error",
                "error_type": type(error).__name__,
            },
        )


@lru_cache
def get_langfuse_handler() -> CallbackHandler:
    if not get_client().auth_check():
        LOG.warning(
            "Langfuse auth check failed — traces will not appear. "
            "Verify LANGFUSE_PUBLIC_KEY / SECRET_KEY / HOST."
        )
    else:
        LOG.info("Langfuse auth OK")
    return CallbackHandler()


@lru_cache
def get_tool_call_logger() -> ToolCallLogger:
    return ToolCallLogger()
