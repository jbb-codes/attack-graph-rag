"""The one thing the rest of the app needs from a language model.

An LLM (large language model) takes text in and writes text back. We hide
every provider behind a single method, so tests use a fake and a real
provider can be swapped in later without touching the pipeline.
"""

import json
import re
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol


class LLMError(Exception):
    """The model could not produce a reply (network, quota, bad response, ...)."""


class LLM(Protocol):
    def complete(self, system: str, prompt: str) -> str:
        """`system` holds fixed rules; `prompt` holds the question and facts."""
        ...


class OfflineLLM:
    """Key-free stand-in (provider "offline") for trying the CLI without a model.

    Writes no new prose: it restates the first fact it was given and cites it.
    """

    _FIRST_FACT = re.compile(r"^\[(T\d{4}(?:\.\d{3})?)\] (.+)$", re.MULTILINE)

    def complete(self, system: str, prompt: str) -> str:
        match = self._FIRST_FACT.search(prompt)
        if match is None:
            return "No matching facts were supplied."
        return f"Closest match: {match.group(2)} [{match.group(1)}]."


MAX_REPLY_TOKENS = 4096
REQUEST_TIMEOUT_SECONDS = 60


class ClaudeLLM:
    """Claude through the official Anthropic SDK.

    The client is passed in, so tests give it a fake and never touch the network.
    """

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def complete(self, system: str, prompt: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_REPLY_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            # The SDK's message can carry request details; callers only need "it failed".
            raise LLMError("Claude request failed") from None
        if response.stop_reason == "refusal":
            raise LLMError("Claude declined to answer")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LLMError("Claude returned no text")
        return text


Post = Callable[[str, dict[str, Any]], dict[str, Any]]


def http_post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    # URL is checked to be http(s) in config.py, so file: and custom schemes cannot reach here.
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # nosec B310
        return json.load(response)


class LocalLLM:
    """A model on your own machine, via the OpenAI-style chat API that Ollama and llama.cpp both offer."""

    def __init__(self, base_url: str, model: str, post: Post = http_post_json) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._post = post

    def complete(self, system: str, prompt: str) -> str:
        body = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        try:
            text = self._post(self._url, body)["choices"][0]["message"]["content"]
        except Exception:
            raise LLMError("Local model request failed") from None
        if not isinstance(text, str) or not text.strip():
            raise LLMError("Local model returned no text")
        return text.strip()
