"""Settings read from environment variables, checked once at startup.

Secrets live only in the environment: never in code, files in git, or messages.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from attack_graph.llm import LLM, ClaudeLLM, LocalLLM, OfflineLLM

PROVIDERS = ("claude", "local", "offline")
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
DEFAULT_LOCAL_URL = "http://localhost:11434/v1"


class ConfigError(Exception):
    """A setting is missing or invalid. The message names the variable, never its value."""


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    # repr=False keeps the key out of logs and tracebacks that print this object.
    api_key: str = field(default="", repr=False)
    claude_model: str = DEFAULT_CLAUDE_MODEL
    local_url: str = DEFAULT_LOCAL_URL
    local_model: str = ""


def load_llm_settings(env: Mapping[str, str]) -> LLMSettings:
    def get(name: str, default: str = "") -> str:
        return env.get(name, "").strip() or default

    provider = get("ATTACK_GRAPH_LLM", "claude").lower()
    if provider not in PROVIDERS:
        raise ConfigError(f"ATTACK_GRAPH_LLM must be one of: {', '.join(PROVIDERS)}.")

    settings = LLMSettings(
        provider=provider,
        api_key=get("ANTHROPIC_API_KEY"),
        claude_model=get("ATTACK_GRAPH_CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
        local_url=get("ATTACK_GRAPH_LOCAL_URL", DEFAULT_LOCAL_URL),
        local_model=get("ATTACK_GRAPH_LOCAL_MODEL"),
    )
    if provider == "claude" and not settings.api_key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Export it, or set ATTACK_GRAPH_LLM=local or offline (see .env.example)."
        )
    if provider == "local" and not settings.local_model:
        raise ConfigError("ATTACK_GRAPH_LOCAL_MODEL is not set (the model name your local server serves).")
    return settings


def build_llm(settings: LLMSettings) -> LLM:
    if settings.provider == "offline":
        return OfflineLLM()
    if settings.provider == "local":
        return LocalLLM(settings.local_url, settings.local_model)
    # Imported here so offline and local runs never pay for loading the SDK.
    from anthropic import Anthropic

    return ClaudeLLM(Anthropic(api_key=settings.api_key), settings.claude_model)
