"""Settings read from environment variables, checked once at startup.

Secrets live only in the environment: never in code, files in git, or messages.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

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
        local_url=_http_url(env, "ATTACK_GRAPH_LOCAL_URL") or DEFAULT_LOCAL_URL,
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


@dataclass(frozen=True)
class StoreSettings:
    """Where the graph and vectors live. None means "in this process, on local disk"."""

    sparql_url: str | None = None
    chroma_url: str | None = None


def load_store_settings(env: Mapping[str, str]) -> StoreSettings:
    return StoreSettings(
        sparql_url=_http_url(env, "ATTACK_GRAPH_SPARQL_URL"),
        chroma_url=_http_url(env, "ATTACK_GRAPH_CHROMA_URL"),
    )


def _http_url(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    if not value:
        return None
    try:
        parts = urlsplit(value)
        valid = parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username
        parts.port  # raises ValueError when the port is not a number
    except ValueError:
        valid = False
    if not valid:
        # Name the variable only: the value may hold a credential.
        raise ConfigError(f"{name} must be an http:// or https:// address with no username or password.")
    return value
