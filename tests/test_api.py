"""HTTP behavior, driven through the app with a fake LLM and the bundled fixture."""

import logging
from importlib.resources import as_file, files

import pytest
from fastapi.testclient import TestClient

from attack_graph.answer import Answerer
from attack_graph.api import MAX_BODY_BYTES, RateLimit, create_app
from attack_graph.graph import AttackGraph
from attack_graph.llm import LLMError
from attack_graph.vector import ChromaVectorStore
from fake_embedder import fake_word_embed
from fake_llm import FakeLLM, ScriptedLLM

POWERSHELL_QUESTION = "Which techniques use PowerShell to run commands and scripts on Windows?"
SHAPE = {"success", "data", "error"}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_client(tmp_path, clock):
    def build(llm=None, *, indexed=True, limit=RateLimit(max_requests=100, window_seconds=60)) -> TestClient:
        with as_file(files("attack_graph") / "data" / "attack_fixture.json") as path:
            graph = AttackGraph.from_stix_file(path)
        store = ChromaVectorStore(tmp_path / "chroma", fake_word_embed)
        if indexed:
            store.index(graph.technique_docs())
        app = create_app(Answerer(store, graph, llm or FakeLLM()), rate_limit=limit, clock=clock)
        return TestClient(app, raise_server_exceptions=False)

    return build


def test_answered_question_uses_shared_shape(make_client):
    response = make_client().post("/ask", json={"question": POWERSHELL_QUESTION})

    body = response.json()
    assert response.status_code == 200
    assert set(body) == SHAPE
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["status"] == "answered"
    assert "[T1059.001]" in body["data"]["answer"]
    assert body["data"]["cited"] == [{"attack_id": "T1059.001", "name": "PowerShell"}]
    assert {"attack_id": "T1059.001", "name": "PowerShell"} in body["data"]["retrieved"]


def test_unsupported_question_is_a_successful_not_found(make_client):
    llm = FakeLLM()

    response = make_client(llm).post("/ask", json={"question": "how to bake sourdough bread"})

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["status"] == "not_found"
    assert llm.calls == []


def test_blank_question_fails_with_same_shape(make_client):
    response = make_client().post("/ask", json={"question": "   "})

    body = response.json()
    assert response.status_code == 400
    assert set(body) == SHAPE
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "invalid_question"
    assert "empty" in body["error"]["message"]


def test_overlong_question_is_rejected_without_calling_llm(make_client):
    llm = FakeLLM()

    response = make_client(llm).post("/ask", json={"question": "a" * 501})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_question"
    assert llm.calls == []


def test_oversized_body_is_rejected(make_client):
    big = {"question": "a" * (MAX_BODY_BYTES + 1)}

    response = make_client().post("/ask", json=big)

    body = response.json()
    assert response.status_code == 413
    assert set(body) == SHAPE
    assert body["error"]["code"] == "payload_too_large"


@pytest.mark.parametrize(
    "payload",
    [{}, {"question": 5}, {"question": None}, {"question": ["x"]}, []],
)
def test_malformed_body_is_a_clean_400(make_client, payload):
    response = make_client().post("/ask", json=payload)

    body = response.json()
    assert response.status_code == 400
    assert set(body) == SHAPE
    assert body["error"]["code"] == "invalid_request"
    # Framework validation detail (field paths, input echo) must not leak.
    assert "loc" not in str(body)


def test_non_json_body_is_a_clean_400(make_client):
    response = make_client().post("/ask", content=b"not json", headers={"content-type": "application/json"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_rate_limit_blocks_then_recovers(make_client, clock):
    client = make_client(limit=RateLimit(max_requests=2, window_seconds=60))
    ask = lambda: client.post("/ask", json={"question": POWERSHELL_QUESTION})  # noqa: E731

    assert ask().status_code == 200
    assert ask().status_code == 200
    blocked = ask()

    assert blocked.status_code == 429
    assert set(blocked.json()) == SHAPE
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(blocked.headers["retry-after"]) <= 60

    clock.now += 61
    assert ask().status_code == 200


def test_rate_limit_does_not_apply_to_health(make_client):
    client = make_client(limit=RateLimit(max_requests=1, window_seconds=60))

    assert all(client.get("/health").status_code == 200 for _ in range(5))


def test_llm_failure_returns_generic_error(make_client):
    llm = ScriptedLLM(LLMError("secret-detail: key sk-123 rejected"))

    response = make_client(llm).post("/ask", json={"question": POWERSHELL_QUESTION})

    body = response.json()
    assert response.status_code == 502
    assert set(body) == SHAPE
    assert body["success"] is False
    assert body["error"]["code"] == "answer_failed"
    assert "sk-123" not in response.text


def test_unexpected_crash_leaks_no_internals_and_logs_no_question(make_client, caplog):
    llm = ScriptedLLM(RuntimeError("db password hunter2 at /srv/app/secret.py"))

    with caplog.at_level(logging.INFO):
        response = make_client(llm).post("/ask", json={"question": POWERSHELL_QUESTION})

    body = response.json()
    assert response.status_code == 500
    assert set(body) == SHAPE
    assert body["error"] == {"code": "internal_error", "message": "Something went wrong."}
    for leaked in ("hunter2", "Traceback", "secret.py", "RuntimeError"):
        assert leaked not in response.text
    assert "hunter2" not in caplog.text
    assert POWERSHELL_QUESTION not in caplog.text


def test_missing_index_is_503_with_setup_hint(make_client):
    response = make_client(indexed=False).post("/ask", json={"question": POWERSHELL_QUESTION})

    body = response.json()
    assert response.status_code == 503
    assert body["error"]["code"] == "not_ready"
    assert "/" not in body["error"]["message"]  # no filesystem paths


def test_unknown_route_and_wrong_method_use_shared_shape(make_client):
    client = make_client()

    missing = client.get("/nope")
    wrong_method = client.get("/ask")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert wrong_method.status_code == 405
    assert set(wrong_method.json()) == SHAPE


def test_health_reports_ok(make_client):
    response = make_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"status": "ok"}, "error": None}


def test_responses_carry_security_headers(make_client):
    for response in (make_client().get("/health"), make_client().post("/ask", json={})):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["cache-control"] == "no-store"
        assert "default-src 'none'" in response.headers["content-security-policy"]


def test_interactive_docs_are_not_exposed(make_client):
    client = make_client()

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
