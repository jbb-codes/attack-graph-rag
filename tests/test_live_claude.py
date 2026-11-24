"""Hits the real Claude API. Opt-in: needs ANTHROPIC_API_KEY and `pytest -m live`."""

import os

import pytest

from attack_graph.config import build_llm, load_llm_settings

pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
def test_real_claude_follows_the_citation_rule():
    llm = build_llm(load_llm_settings({**os.environ, "ATTACK_GRAPH_LLM": "claude"}))

    reply = llm.complete(
        "Answer from the facts only and cite technique IDs in square brackets.",
        "<question>What is T1059.001?</question>\n<facts>\n[T1059.001] PowerShell: runs commands on Windows.\n</facts>",
    )

    assert "[T1059.001]" in reply
