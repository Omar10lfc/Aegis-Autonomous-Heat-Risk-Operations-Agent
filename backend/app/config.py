from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fortyguard_api_key: str = ""
    fortyguard_base_url: str = "https://api.fortyguard.com"
    fortyguard_max_aoi_mi2: float = 10.0
    fortyguard_live: bool = False

    # LLM providers: "groq" (primary, JSON mode, ~$0.001/run) then "openrouter" (free tier).
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"
    groq_fallback_models: str = "qwen/qwen3.6-27b"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Free-tier slugs only (enforced). Verified live 2026-08-25.
    openrouter_model: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    openrouter_fallback_models: str = "google/gemma-4-26b-a4b-it:free,minimax/minimax-m2.7:free"

    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "fortyguard-aegis"
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langchain_eval_project: str = "fortyguard-aegis-eval"

    aegis_host: str = "0.0.0.0"
    aegis_port: int = 8000
    aegis_poll_timeout_seconds: float = 180.0
    aegis_max_retries: int = 3
    aegis_initial_poll_delay_seconds: float = 3.0
    aegis_max_poll_delay_seconds: float = 30.0
    aegis_llm_mode: str = "auto"
    # Template memo by default: deterministic, always cited, instant. LLM polish is opt-in.
    aegis_synth_llm: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce_empty_strings(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Vercel/Heroku set unset env vars as empty strings.
        Pydantic rejects '' for bool/int/float fields, so we drop them
        to let defaults apply."""
        if not isinstance(values, dict):
            return values
        bool_fields = {"fortyguard_live", "langchain_tracing_v2", "aegis_synth_llm"}
        numeric_fields = {
            "fortyguard_max_aoi_mi2", "aegis_port",
            "aegis_poll_timeout_seconds", "aegis_max_retries",
            "aegis_initial_poll_delay_seconds", "aegis_max_poll_delay_seconds",
        }
        drop_if_empty = bool_fields | numeric_fields
        for key in drop_if_empty:
            if key in values and values[key] == "":
                del values[key]
            # Also check uppercase variants (env vars)
            upper = key.upper()
            if upper in values and values[upper] == "":
                del values[upper]
        return values

    def tracing_endpoint(self) -> str:
        return self.langsmith_endpoint or self.langchain_endpoint

    @property
    def llm_available(self) -> bool:
        return bool(self.groq_api_key or self.openrouter_api_key)

    def _model_list(self, primary: str, fallbacks: str) -> list[str]:
        models = [primary]
        for item in fallbacks.split(","):
            slug = item.strip()
            if slug and slug not in models:
                models.append(slug)
        return models

    def provider_chain(self) -> list[dict[str, Any]]:
        """Ordered LLM providers: configured primary first, then the other (if keyed)."""
        groq = {
            "provider": "groq",
            "api_key": self.groq_api_key,
            "base_url": self.groq_base_url,
            "models": self._model_list(self.groq_model, self.groq_fallback_models),
            "json_mode": True,
        }
        openrouter = {
            "provider": "openrouter",
            "api_key": self.openrouter_api_key,
            "base_url": self.openrouter_base_url,
            "models": self._model_list(self.openrouter_model, self.openrouter_fallback_models),
            "json_mode": False,
        }
        chain: list[dict[str, Any]] = []
        if self.llm_provider == "openrouter":
            chain = [openrouter, groq]
        else:
            chain = [groq, openrouter]
        return [p for p in chain if p["api_key"]]

    def primary_model_label(self) -> str:
        chain = self.provider_chain()
        if not chain:
            return "heuristic"
        return f"{chain[0]['provider']}:{chain[0]['models'][0]}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
