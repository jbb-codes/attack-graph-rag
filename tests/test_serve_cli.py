from fastapi.testclient import TestClient

from attack_graph.cli import main
from fake_embedder import fake_word_embed
from fake_llm import FakeLLM


def serve(capsys, *argv: str, env=None):
    started = {}

    def run_server(app, host, port):
        started.update(app=app, host=host, port=port)

    code = main(["serve", *argv], embed=fake_word_embed, llm=FakeLLM(), env=env or {}, run_server=run_server)
    return code, started, capsys.readouterr().err


def test_serve_binds_to_localhost_by_default_and_answers(capsys):
    main(["index"], embed=fake_word_embed)

    code, started, _ = serve(capsys)

    assert code == 0
    assert (started["host"], started["port"]) == ("127.0.0.1", 8000)
    response = TestClient(started["app"]).post("/ask", json={"question": "PowerShell scripts on Windows"})
    assert response.json()["success"] is True


def test_serve_accepts_host_and_port(capsys):
    _, started, _ = serve(capsys, "--host", "0.0.0.0", "--port", "9000")

    assert (started["host"], started["port"]) == ("0.0.0.0", 9000)


def test_serve_fails_fast_when_llm_not_configured(capsys):
    started = {}
    code = main(["serve"], embed=fake_word_embed, env={}, run_server=lambda *a: started.update(ran=True))

    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert started == {}
