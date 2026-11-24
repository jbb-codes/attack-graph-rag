"""Fake LLMs for tests: no network, fully deterministic, and they record what they were sent."""

import re

_FACT_ID = re.compile(r"^\[(T\d{4}(?:\.\d{3})?)\]", re.MULTILINE)


class FakeLLM:
    """Behaves like a well-behaved model: answers from the first fact it was given and cites it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        ids = _FACT_ID.findall(prompt)
        return f"Answer based on the supplied facts [{ids[0]}]." if ids else "No facts."


class ScriptedLLM:
    """Returns a fixed reply (or raises it, if it is an exception)."""

    def __init__(self, reply: str | Exception) -> None:
        self._reply = reply
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply
