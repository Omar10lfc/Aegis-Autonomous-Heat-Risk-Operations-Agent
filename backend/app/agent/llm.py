"""Provider-aware LLM client (Groq primary, OpenRouter free-tier fallback) with 429 backoff."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr, ValidationError

from app.config import Settings
from app.tools.redact import redact_value

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def build_chat_model(settings: Settings, provider: dict[str, Any], model: str) -> ChatOpenAI:
    if provider["provider"] == "openrouter" and not model.endswith(":free"):
        raise LLMError(f"Refusing non-free OpenRouter model: {model}")
    kwargs: dict[str, Any] = {}
    if provider.get("json_mode"):
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(provider["api_key"]),
        base_url=provider["base_url"],
        temperature=0,
        max_tokens=2000,
        timeout=60,
        max_retries=0,
        default_headers={
            "HTTP-Referer": "https://github.com/FortyGuard-Tech/temperature-api-quickstart",
            "X-Title": "Aegis FortyGuard Agent",
        },
        **kwargs,
    )


async def complete_json(
    settings: Settings,
    *,
    system: str,
    user: str,
    schema: type[BaseModel],
) -> tuple[BaseModel, str]:
    last_error: str | None = None
    for provider in settings.provider_chain():
        for model in provider["models"]:
            try:
                llm = build_chat_model(settings, provider, model)
            except LLMError as exc:
                last_error = str(exc)
                continue
            delay = 2.0
            for attempt in range(1, settings.aegis_max_retries + 1):
                try:
                    message = await llm.ainvoke(
                        [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ]
                    )
                    parsed = _parse_json_message(message.content, schema)
                    return parsed, f"{provider['provider']}:{model}"
                except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                    last_error = f"{provider['provider']}:{model} invalid JSON: {exc}"
                    logger.warning("structured output failed for %s", f"{provider['provider']}:{model}")
                    break
                except Exception as exc:
                    last_error = f"{provider['provider']}:{model}: {exc}"
                    text = str(exc)
                    if "429" not in text and "rate" not in text.lower():
                        logger.warning("llm error on %s: %s", f"{provider['provider']}:{model}", redact_value(text))
                        break
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 20.0)
    raise LLMError(last_error or "all LLM providers failed")


def _parse_json_message(content: Any, schema: type[BaseModel]) -> BaseModel:
    text = content if isinstance(content, str) else str(content)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model reply did not contain a JSON object")
    return schema.model_validate(json.loads(text[start : end + 1]))
