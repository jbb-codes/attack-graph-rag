from attack_graph.cli import main
from fake_embedder import fake_word_embed
from fake_llm import FakeLLM


def run(capsys, *argv: str, llm=None) -> tuple[int, str, str]:
    code = main(list(argv), embed=fake_word_embed, llm=llm or FakeLLM())
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_ask_prints_answer_and_cited_techniques(capsys):
    run(capsys, "index")

    code, out, _ = run(capsys, "ask", "Which techniques use PowerShell to run commands and scripts on Windows?")

    assert code == 0
    assert "[T1059.001]" in out
    assert "Cited:\n  T1059.001 PowerShell" in out
    assert "Retrieved:" in out


def test_unsupported_question_prints_not_found_and_exits_1(capsys):
    llm = FakeLLM()
    run(capsys, "index")

    code, out, _ = run(capsys, "ask", "how to bake sourdough bread", llm=llm)

    assert code == 1
    assert "Not found" in out
    assert llm.calls == []


def test_blank_question_exits_2_with_message(capsys):
    run(capsys, "index")

    code, out, err = run(capsys, "ask", "  ")

    assert code == 2
    assert "empty" in (out + err)


def test_ask_before_index_says_to_run_index(capsys):
    code, _, err = run(capsys, "ask", "PowerShell")

    assert code == 2
    assert "attack-graph index" in err
