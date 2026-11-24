"""Real providers, driven through `ask` with a fake network underneath."""

from types import SimpleNamespace

import pytest

from attack_graph.answer import Answerer
from attack_graph.graph import AttackGraph
from attack_graph.llm import ClaudeLLM, LocalLLM
from attack_graph.vector import ChromaVectorStore
from fake_embedder import fake_word_embed

QUESTION = "Which techniques use PowerShell to run commands and scripts on Windows?"


@pytest.fixture
def answerer_for(tmp_path):
    from importlib.resources import as_file, files

    with as_file(files("attack_graph") / "data" / "attack_fixture.json") as path:
        graph = AttackGraph.from_stix_file(path)
    store = ChromaVectorStore(tmp_path / "chroma", fake_word_embed)
    store.index(graph.technique_docs())
    return lambda llm: Answerer(store, graph, llm)


class FakeAnthropic:
    """Mimics `client.messages.create(...)`; records the request."""

    def __init__(self, reply=None, error: Exception | None = None, stop_reason="end_turn"):
        self.requests: list[dict] = []
        self._reply, self._error, self._stop = reply, error, stop_reason
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if self._error:
            raise self._error
        content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self._reply)]
        return SimpleNamespace(content=content, stop_reason=self._stop)


def test_claude_reply_becomes_a_cited_answer(answerer_for):
    client = FakeAnthropic("PowerShell is covered by T1059.001.")

    answer = answerer_for(ClaudeLLM(client, "claude-test")).ask(QUESTION)

    assert answer.status == "answered"
    assert [ref.attack_id for ref in answer.cited] == ["T1059.001"]


def test_claude_gets_rules_as_system_and_question_as_user_message(answerer_for):
    client = FakeAnthropic("See T1059.001.")

    answerer_for(ClaudeLLM(client, "claude-test")).ask(QUESTION)

    request = client.requests[0]
    assert request["model"] == "claude-test"
    assert QUESTION not in request["system"]
    assert QUESTION in request["messages"][0]["content"]
    assert request["messages"][0]["role"] == "user"


def test_claude_failure_becomes_a_generic_error_answer(answerer_for):
    client = FakeAnthropic(error=RuntimeError("401 key sk-ant-leak"))

    answer = answerer_for(ClaudeLLM(client, "claude-test")).ask(QUESTION)

    assert answer.status == "error"
    assert "sk-ant-leak" not in answer.text


def test_claude_refusal_is_an_error_not_an_empty_answer(answerer_for):
    client = FakeAnthropic(reply="", stop_reason="refusal")

    assert answerer_for(ClaudeLLM(client, "claude-test")).ask(QUESTION).status == "error"


def test_local_model_reply_becomes_a_cited_answer(answerer_for):
    sent: list[tuple[str, dict]] = []

    def post(url: str, body: dict) -> dict:
        sent.append((url, body))
        return {"choices": [{"message": {"content": "Use T1059.001."}}]}

    answer = answerer_for(LocalLLM("http://localhost:11434/v1", "llama-test", post)).ask(QUESTION)

    assert answer.status == "answered"
    assert sent[0][0] == "http://localhost:11434/v1/chat/completions"
    assert sent[0][1]["model"] == "llama-test"


def test_local_server_down_becomes_a_generic_error_answer(answerer_for):
    def post(url: str, body: dict) -> dict:
        raise OSError("connection refused")

    assert answerer_for(LocalLLM("http://x/v1", "m", post)).ask(QUESTION).status == "error"
