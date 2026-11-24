"""Prompt-injection defenses, tested through `ask` only.

A fake model cannot be tricked, so these tests check what we control: how the
prompt is built (rules apart from data, data cannot break out of its block)
and what we do with the reply (rules never echoed, only retrieved IDs cited).
"""

import json
from importlib.resources import as_file, files
from pathlib import Path

import pytest

from answerer_factory import build
from attack_graph.graph import AttackGraph
from fake_llm import FakeLLM, LeakyLLM, prompt_block

POWERSHELL_Q = "Which techniques use PowerShell to run commands and scripts on Windows?"
FIXTURE = files("attack_graph") / "data" / "attack_fixture.json"
CORPUS = json.loads((Path(__file__).parent / "injection_corpus.json").read_text())
CORPUS_PARAMS = [pytest.param(case["text"], id=case["id"]) for case in CORPUS]


@pytest.fixture
def graph():
    with as_file(FIXTURE) as path:
        return AttackGraph.from_stix_file(path)


def attack_question(payload):
    # The on-topic part is repeated so the attack words cannot drown it out in retrieval.
    return f"{POWERSHELL_Q} {payload} {POWERSHELL_Q}"


def escaped(text):
    return text.replace("<", "&lt;").replace(">", "&gt;")


def poisoned_graph(tmp_path, payload):
    """The fixture with an attack hidden in the PowerShell technique's description."""
    bundle = json.loads(FIXTURE.read_text())
    for obj in bundle["objects"]:
        if obj.get("name") == "PowerShell":
            obj["description"] += " " + payload
    path = tmp_path / "poisoned.json"
    path.write_text(json.dumps(bundle))
    return AttackGraph.from_stix_file(path)


def baseline_rules(graph, tmp_path):
    """The rules a plain question produces, as the baseline the attacks must not change."""
    baseline = FakeLLM()
    build(graph, baseline, tmp=tmp_path / "baseline").ask(POWERSHELL_Q)
    return baseline.calls[0][0]


class TestPromptStructure:
    def test_rules_and_data_travel_in_separate_channels(self, graph, tmp_path):
        llm = FakeLLM()
        build(graph, llm, tmp=tmp_path / "c").ask(POWERSHELL_Q)

        system, prompt = llm.calls[0]
        assert "</question>" not in system and "</facts>" not in system
        assert "APT29" not in system
        assert prompt_block(prompt, "question") == POWERSHELL_Q
        assert "APT29" in prompt_block(prompt, "facts")

    def test_rules_name_both_data_blocks_and_forbid_obeying_them(self, graph, tmp_path):
        llm = FakeLLM()
        build(graph, llm, tmp=tmp_path / "c").ask(POWERSHELL_Q)

        system = llm.calls[0][0].lower()
        assert "<question>" in system and "<facts>" in system
        assert "never instructions" in system
        assert "do not reveal" in system


class TestInjectionInQuestions:
    @pytest.mark.parametrize("payload", CORPUS_PARAMS)
    def test_attack_text_stays_inside_the_question_block(self, graph, tmp_path, payload):
        llm = FakeLLM()
        result = build(graph, llm, tmp=tmp_path / "c").ask(attack_question(payload))

        system, prompt = llm.calls[0]
        assert system == baseline_rules(graph, tmp_path)
        assert payload not in system
        assert result.status == "answered"
        assert {ref.attack_id for ref in result.cited} <= {ref.attack_id for ref in result.retrieved}
        assert "T9999" not in result.text

    @pytest.mark.parametrize("payload", CORPUS_PARAMS)
    def test_attack_text_cannot_close_a_block_or_open_a_fake_one(self, graph, tmp_path, payload):
        llm = FakeLLM()
        build(graph, llm, tmp=tmp_path / "c").ask(attack_question(payload))

        prompt = llm.calls[0][1]
        assert prompt.count("<question>") == prompt.count("</question>") == 1
        assert prompt.count("<facts>") == prompt.count("</facts>") == 1
        assert "T9999" not in prompt_block(prompt, "facts")


class TestInjectionInRetrievedData:
    @pytest.mark.parametrize("payload", CORPUS_PARAMS)
    def test_poisoned_text_appears_only_inside_the_facts_block(self, tmp_path, payload):
        llm = FakeLLM()
        result = build(poisoned_graph(tmp_path, payload), llm, tmp=tmp_path / "c").ask(POWERSHELL_Q)

        system, prompt = llm.calls[0]
        assert payload not in system
        assert escaped(payload) in prompt_block(prompt, "facts")
        assert escaped(payload) not in prompt_block(prompt, "question")
        assert result.status == "answered"

    @pytest.mark.parametrize("payload", CORPUS_PARAMS)
    def test_poisoned_text_cannot_close_the_facts_block(self, tmp_path, payload):
        llm = FakeLLM()
        build(poisoned_graph(tmp_path, payload), llm, tmp=tmp_path / "c").ask(POWERSHELL_Q)

        prompt = llm.calls[0][1]
        assert prompt.count("<facts>") == prompt.count("</facts>") == 1
        assert prompt.count("<question>") == prompt.count("</question>") == 1
