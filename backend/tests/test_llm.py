"""Provider chain, JSON mode, and gating tests for the LLM layer."""

from __future__ import annotations

import pytest

from app.agent.llm import LLMError, build_chat_model, complete_json
from app.config import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        groq_api_key="",
        openrouter_api_key="",
        llm_provider="groq",
        aegis_llm_mode="auto",
        aegis_max_retries=2,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_chain_groq_first_when_configured():
    s = _settings(groq_api_key="gsk_test", openrouter_api_key="sk-or-v1-test")
    chain = s.provider_chain()
    assert [p["provider"] for p in chain] == ["groq", "openrouter"]
    assert chain[0]["json_mode"] is True
    assert chain[0]["models"][0] == "openai/gpt-oss-20b"
    assert "qwen/qwen3.6-27b" in chain[0]["models"]


def test_chain_openrouter_primary_when_selected():
    s = _settings(groq_api_key="gsk_test", openrouter_api_key="sk-or-v1-test", llm_provider="openrouter")
    assert [p["provider"] for p in s.provider_chain()] == ["openrouter", "groq"]


def test_chain_skips_unkeyed_providers():
    s = _settings(groq_api_key="gsk_test")
    assert [p["provider"] for p in s.provider_chain()] == ["groq"]


def test_llm_available_and_label():
    assert _settings().llm_available is False
    s = _settings(groq_api_key="gsk_test")
    assert s.llm_available is True
    assert s.primary_model_label() == "groq:openai/gpt-oss-20b"


def test_openrouter_refuses_non_free_model():
    s = _settings(openrouter_api_key="sk-or-v1-test")
    provider = s.provider_chain()[0]
    with pytest.raises(LLMError, match="non-free"):
        build_chat_model(s, provider, "openai/gpt-oss-20b")


def test_groq_model_gets_json_mode():
    s = _settings(groq_api_key="gsk_test")
    provider = s.provider_chain()[0]
    llm = build_chat_model(s, provider, "openai/gpt-oss-20b")
    assert llm.model_kwargs.get("response_format") == {"type": "json_object"}


@pytest.mark.asyncio
async def test_complete_json_falls_through_to_second_provider(monkeypatch):
    s = _settings(groq_api_key="gsk_dead", openrouter_api_key="sk-or-v1-test")

    class FakeMsg:
        content = '{"markdown": "ok"}'

    class FakeLLM:
        def __init__(self, provider_key):
            self.provider_key = provider_key

        async def ainvoke(self, messages):
            if self.provider_key == "groq":
                raise RuntimeError("HTTP 404 model gone")
            return FakeMsg()

    import app.agent.llm as llm_mod

    def fake_build(settings, provider, model):
        return FakeLLM(provider["provider"])

    monkeypatch.setattr(llm_mod, "build_chat_model", fake_build)

    from pydantic import BaseModel

    class MemoDraft(BaseModel):
        markdown: str

    parsed, label = await complete_json(s, system="s", user="u", schema=MemoDraft)
    assert parsed.markdown == "ok"
    assert label.startswith("openrouter:")
