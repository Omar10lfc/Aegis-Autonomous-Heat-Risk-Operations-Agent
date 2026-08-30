"""Keep API keys out of logs, traces, and LangSmith spans."""

from __future__ import annotations

import re
from typing import Any

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "fortyguard_api_key",
    "openrouter_api_key",
    "openai_api_key",
    "groq_api_key",
    "gsk",
    "langchain_api_key",
    "authorization",
    "api-key",
}

_SECRET_RE = re.compile(
    r"(sk-or-v1-[A-Za-z0-9]+|gsk_[A-Za-z0-9]+|lsv2_[A-Za-z0-9_]+|Bearer\s+\S+)",
    re.IGNORECASE,
)


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): ("[redacted]" if str(k).lower().replace("-", "_") in _SECRET_KEYS else redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return _SECRET_RE.sub("[redacted]", value)
    return value


def redact_mapping(inputs: dict[str, Any]) -> dict[str, Any]:
    return redact_value(inputs)
