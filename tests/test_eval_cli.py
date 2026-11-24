"""`attack-graph eval` end to end with a fake model: no key, no network."""

import json
from pathlib import Path

from attack_graph.cli import main
from fake_embedder import fake_word_embed
from fake_llm import FakeLLM

ROOT = Path(__file__).resolve().parent.parent
POWERSHELL_Q = "Which techniques use PowerShell to run commands and scripts on Windows?"


def write_cases(tmp_path, cases) -> str:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    return str(path)


def run(capsys, *argv, llm=None):
    code = main(list(argv), embed=fake_word_embed, llm=llm or FakeLLM(), env={})
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def passing_case():
    return {"id": "ps", "kind": "specific", "question": POWERSHELL_Q, "expect_status": "answered", "cited_all": ["T1059.001"]}


def test_prints_summary_saves_results_and_exits_0_when_all_pass(capsys, tmp_path):
    run(capsys, "index")
    cases = write_cases(tmp_path, [passing_case()])
    results = tmp_path / "results"

    code, out, _ = run(capsys, "eval", "--cases", cases, "--corpus", str(tmp_path / "none.json"), "--results-dir", str(results))

    assert code == 0
    assert "1/1" in out
    assert len(list(results.glob("*.json"))) == 1


def test_exits_1_and_names_the_failing_case(capsys, tmp_path):
    run(capsys, "index")
    failing = {**passing_case(), "id": "wrong", "cited_all": ["T1003"]}
    cases = write_cases(tmp_path, [failing])

    code, out, _ = run(capsys, "eval", "--cases", cases, "--corpus", str(tmp_path / "none.json"), "--results-dir", str(tmp_path / "r"))

    assert code == 1
    assert "wrong" in out


def test_second_run_is_compared_with_the_first(capsys, tmp_path):
    run(capsys, "index")
    cases = write_cases(tmp_path, [passing_case()])
    args = ("eval", "--cases", cases, "--corpus", str(tmp_path / "none.json"), "--results-dir", str(tmp_path / "r"))
    run(capsys, *args)

    _, out, _ = run(capsys, *args)

    assert "Compared with previous run" in out


def test_includes_injection_cases_from_the_corpus(capsys, tmp_path):
    run(capsys, "index")
    cases = write_cases(tmp_path, [passing_case()])
    corpus = ROOT / "tests" / "injection_corpus.json"

    code, out, _ = run(capsys, "eval", "--cases", cases, "--corpus", str(corpus), "--results-dir", str(tmp_path / "r"))

    assert code == 0
    assert f"/{1 + len(json.loads(corpus.read_text()))}" in out
    assert "injection" in out


def test_bad_cases_file_exits_2_with_message(capsys, tmp_path):
    run(capsys, "index")
    bad = tmp_path / "bad.json"
    bad.write_text("nope")

    code, _, err = run(capsys, "eval", "--cases", str(bad), "--results-dir", str(tmp_path / "r"))

    assert code == 2
    assert "bad.json" in err


def test_eval_before_index_says_to_run_index(capsys, tmp_path):
    cases = write_cases(tmp_path, [passing_case()])

    code, _, err = run(capsys, "eval", "--cases", cases, "--results-dir", str(tmp_path / "r"))

    assert code == 2
    assert "attack-graph index" in err


def test_eval_with_claude_needs_a_key_before_anything_runs(capsys, tmp_path):
    cases = write_cases(tmp_path, [passing_case()])

    code = main(["eval", "--cases", cases], env={})
    err = capsys.readouterr().err

    assert code == 2
    assert "ANTHROPIC_API_KEY" in err
