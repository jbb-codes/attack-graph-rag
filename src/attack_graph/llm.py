"""The one thing the rest of the app needs from a language model.

An LLM (large language model) takes text in and writes text back. We hide
every provider behind a single method, so tests use a fake and a real
provider can be swapped in later without touching the pipeline.
"""

import re
from typing import Protocol


class LLMError(Exception):
    """The model could not produce a reply (network, quota, bad response, ...)."""


class LLM(Protocol):
    def complete(self, system: str, prompt: str) -> str:
        """`system` holds fixed rules; `prompt` holds the question and facts."""
        ...


class OfflineLLM:
    """Stand-in used by the CLI until a real provider exists (issue #6).

    Writes no new prose: it restates the first fact it was given and cites it.
    """

    _FIRST_FACT = re.compile(r"^\[(T\d{4}(?:\.\d{3})?)\] (.+)$", re.MULTILINE)

    def complete(self, system: str, prompt: str) -> str:
        match = self._FIRST_FACT.search(prompt)
        if match is None:
            return "No matching facts were supplied."
        return f"Closest match: {match.group(2)} [{match.group(1)}]."
