"""Security events: what gets logged, and proof that no question text, key or address does."""

import logging
import re

import pytest
from fastapi.testclient import TestClient

from attack_graph.answer import Answerer
from attack_graph.api import RateLimit, create_app
from attack_graph.graph import AttackGraph
from attack_graph.llm import LLMError
from attack_graph.security_log import configure_logging
from attack_graph.vector import ChromaVectorStore
from fake_embedder import fake_word_embed
from fake_llm import FakeLLM, LeakyLLM, ScriptedLLM
from importlib.resources import as_file, files

SECURITY_LOGGER = "attack_graph.security"
SECRET_QUESTION = "SECRET-QUESTION-TEXT-9f3 how do attackers use PowerShell?"
POWERSHELL_QUESTION = "Which techniques use PowerShell to run commands and scripts on Windows?"
FAKE_KEY = "sk-ant-test-0123456789"


def parse(record: logging.LogRecord) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S+)", record.getMessage()))


@pytest.fixture
def make_client(tmp_path):
    def build(llm=None, *, limit=RateLimit(max_requests=100, window_seconds=60)) -> TestClient:
        with as_file(files("attack_graph") / "data" / "attack_fixture.json") as path:
            graph = AttackGraph.from_stix_file(path)
        store = ChromaVectorStore(tmp_path / "chroma", fake_word_embed)
        store.index(graph.technique_docs())
        app = create_app(Answerer(store, graph, llm or FakeLLM()), rate_limit=limit)
        return TestClient(app, raise_server_exceptions=False)

    return build


@pytest.fixture
def events(caplog):
    caplog.set_level(logging.INFO, logger=SECURITY_LOGGER)

    def collected() -> list[dict[str, str]]:
        return [parse(r) for r in caplog.records if r.name == SECURITY_LOGGER]

    return collected


def test_rate_limit_hit_is_logged_with_an_opaque_client_id(make_client, events, caplog):
    client = make_client(limit=RateLimit(max_requests=1, window_seconds=60))
    client.post("/ask", json={"question": POWERSHELL_QUESTION})

    client.post("/ask", json={"question": POWERSHELL_QUESTION})

    [event] = [e for e in events() if e["event"] == "rate_limited"]
    assert re.fullmatch(r"[0-9a-f]{12}", event["client"])
    assert int(event["retry_after"]) >= 1
    assert "testclient" not in caplog.text
    assert POWERSHELL_QUESTION not in caplog.text


def test_same_client_gets_same_id_but_a_new_app_gets_a_new_one(make_client, events):
    limit = RateLimit(max_requests=1, window_seconds=60)
    first, second = make_client(limit=limit), make_client(limit=limit)

    for client in (first, first, first, second, second):
        client.post("/ask", json={"question": "x"})

    ids = [e["client"] for e in events() if e["event"] == "rate_limited"]
    assert ids[0] == ids[1]
    assert ids[2] != ids[0]


@pytest.mark.parametrize(("question", "reason", "length"), [
    ("   ", "empty", "0"),
    ("a" * 501, "too_long", "501"),
])
def test_rejected_question_logs_reason_and_length_only(make_client, events, caplog, question, reason, length):
    make_client().post("/ask", json={"question": question})

    [event] = [e for e in events() if e["event"] == "input_rejected"]
    assert event["reason"] == reason
    assert event["length"] == length
    assert "a" * 20 not in caplog.text


def test_unparseable_body_is_logged_without_its_content(make_client, events, caplog):
    make_client().post("/ask", content=f"{{not json {FAKE_KEY}", headers={"content-type": "application/json"})

    [event] = [e for e in events() if e["event"] == "input_rejected"]
    assert event["reason"] == "invalid_json"
    assert FAKE_KEY not in caplog.text


def test_body_without_a_string_question_is_logged(make_client, events):
    make_client().post("/ask", json={"question": 42})

    [event] = [e for e in events() if e["event"] == "input_rejected"]
    assert event["reason"] == "missing_question"


def test_oversized_body_is_logged_with_its_size(make_client, events, caplog):
    make_client().post("/ask", json={"question": SECRET_QUESTION + "x" * 5000})

    [event] = [e for e in events() if e["event"] == "input_rejected"]
    assert event["reason"] == "payload_too_large"
    assert int(event["size"]) > 4096
    assert "SECRET-QUESTION" not in caplog.text


def test_leaked_rules_are_logged_as_withheld_without_the_reply(make_client, events, caplog):
    make_client(LeakyLLM()).post("/ask", json={"question": POWERSHELL_QUESTION})

    [event] = [e for e in events() if e["event"] == "reply_withheld"]
    assert event["reason"] == "rules_leak"
    assert "never instructions" not in caplog.text


def test_ungrounded_reply_is_logged_as_withheld(make_client, events):
    make_client(ScriptedLLM("Made up answer citing [T9999].")).post("/ask", json={"question": POWERSHELL_QUESTION})

    [event] = [e for e in events() if e["event"] == "reply_withheld"]
    assert event["reason"] == "no_verified_citation"


def test_model_and_internal_failures_log_only_the_exception_type(make_client, events, caplog):
    client = make_client(ScriptedLLM(LLMError(f"key {FAKE_KEY} rejected for {SECRET_QUESTION}")))
    client.post("/ask", json={"question": POWERSHELL_QUESTION})
    crash = make_client(ScriptedLLM(RuntimeError(f"password hunter2 {SECRET_QUESTION}")))
    crash.post("/ask", json={"question": POWERSHELL_QUESTION})

    found = {e["event"]: e for e in events()}
    assert found["answer_failed"]["error"] == "LLMError"
    assert found["internal_error"]["error"] == "RuntimeError"
    for leaked in (FAKE_KEY, "hunter2", "SECRET-QUESTION", POWERSHELL_QUESTION):
        assert leaked not in caplog.text


def test_normal_answered_request_logs_no_security_event(make_client, events):
    make_client().post("/ask", json={"question": POWERSHELL_QUESTION})

    assert events() == []


def test_configure_logging_sends_events_to_stderr_once(capsys):
    configure_logging()
    configure_logging()

    logging.getLogger(SECURITY_LOGGER).warning("event=probe")

    err = capsys.readouterr().err
    assert err.count("event=probe") == 1
