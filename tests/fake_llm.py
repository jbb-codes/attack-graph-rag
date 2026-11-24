"""Fake LLMs for tests: no network, fully deterministic, and they record what they were sent."""

import re

_FACT_ID = re.compile(r"^\[(T\d{4}(?:\.\d{3})?)\]", re.MULTILINE)


def _facts_part(prompt: str) -> str:
    # A well-behaved model takes facts from the facts block, not from the question.
    return prompt.partition("<facts>")[2]


class FakeLLM:
    """Behaves like a well-behaved model: answers from the first fact it was given and cites it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        ids = _FACT_ID.findall(_facts_part(prompt))
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


_BLOCK = r"<{tag}>\n(.*?)\n</{tag}>"


def prompt_block(prompt: str, tag: str) -> str:
    """The text inside the one <tag>...</tag> block of a prompt, so tests can see where text landed."""
    found = re.findall(_BLOCK.format(tag=tag), prompt, re.DOTALL)
    assert len(found) == 1, f"expected exactly one <{tag}> block, found {len(found)}"
    return found[0]


class LeakyLLM:
    """Worst case: a model that gives in and repeats its rules (still citing a real fact)."""

    def __init__(self, wrap=lambda system: system) -> None:
        self._wrap = wrap

    def complete(self, system: str, prompt: str) -> str:
        ids = _FACT_ID.findall(_facts_part(prompt))
        return f"{self._wrap(system)} [{ids[0]}]"
