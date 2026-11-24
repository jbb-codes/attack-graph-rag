"""Eval scoring, saving and summary: pure code, tested offline. The real-model run is on demand."""

import json
from dataclasses import replace
from datetime import datetime, timezone
from importlib.resources import as_file, files
from pathlib import Path

import pytest

from answerer_factory import build
from attack_graph.answer import Answer
from attack_graph.evals import (
    CaseResult,
    EvalCase,
    EvalError,
    EvalRun,
    injection_cases,
    latest_run,
    load_cases,
    run_evals,
    save_run,
    score_case,
    summarize,
)
from attack_graph.graph import AttackGraph, Ref
from fake_llm import FakeLLM, ScriptedLLM

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "evals" / "questions.json"
CORPUS_FILE = ROOT / "tests" / "injection_corpus.json"
NOW = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)

POWERSHELL_Q = "Which techniques use PowerShell to run commands and scripts on Windows?"


def case(**overrides) -> EvalCase:
    base = EvalCase(id="c1", kind="specific", question="q", expect_status="answered")
    return replace(base, **overrides)


def answered(text="PowerShell runs commands [T1059.001].", cited=("T1059.001",)) -> Answer:
    refs = tuple(Ref(i, "n") for i in cited)
    return Answer("answered", text, cited=refs, retrieved=refs)


class TestScoreCase:
    def test_passes_when_all_expected_ids_are_cited(self):
        result = score_case(case(cited_all=("T1059.001",)), answered())

        assert result.passed
        assert result.failures == ()

    def test_fails_naming_the_missing_id(self):
        result = score_case(case(cited_all=("T1059.001", "T1003")), answered())

        assert not result.passed
        assert any("T1003" in f for f in result.failures)

    def test_cited_any_needs_just_one(self):
        assert score_case(case(cited_any=("T1566", "T1059.001")), answered()).passed
        assert not score_case(case(cited_any=("T1566", "T1003")), answered()).passed

    def test_must_contain_ignores_case_and_punctuation(self):
        answer = answered(text="It is under the Initial-Access tactic [T1059.001].")

        assert score_case(case(must_contain=("initial access",)), answer).passed
        assert not score_case(case(must_contain=("persistence",)), answer).passed

    def test_forbidden_text_fails_the_case(self):
        answer = answered(text="PWNED [T1059.001]")

        result = score_case(case(forbidden=("pwned",)), answer)

        assert not result.passed
        assert any("pwned" in f for f in result.failures)

    def test_wrong_status_fails(self):
        refused = Answer("not_found", "Not found in the ATT&CK data, so no answer was given.")

        assert not score_case(case(expect_status="answered"), refused).passed
        assert score_case(case(expect_status="not_found"), refused).passed

    def test_no_expected_status_accepts_any(self):
        refused = Answer("not_found", "Not found.")

        assert score_case(case(expect_status=None, forbidden=("pwned",)), refused).passed

    def test_result_keeps_what_the_service_said_for_later_comparison(self):
        result = score_case(case(), answered())

        assert (result.status, result.cited, result.retrieved) == ("answered", ("T1059.001",), ("T1059.001",))
        assert "PowerShell" in result.answer


@pytest.fixture
def graph():
    with as_file(files("attack_graph") / "data" / "attack_fixture.json") as path:
        return AttackGraph.from_stix_file(path)


class TestRunEvals:
    def test_runs_every_case_through_ask_and_scores_it(self, graph, tmp_path):
        answerer = build(graph, FakeLLM(), tmp=tmp_path)
        cases = [
            case(id="hit", question=POWERSHELL_Q, cited_all=("T1059.001",)),
            case(id="miss", question="how to bake sourdough bread", expect_status="not_found"),
            case(id="wrong", question=POWERSHELL_Q, cited_all=("T1003",)),
        ]

        run = run_evals(answerer, cases, label="fake", now=NOW)

        assert [r.case_id for r in run.results] == ["hit", "miss", "wrong"]
        assert [r.passed for r in run.results] == [True, True, False]
        assert (run.passed, run.total) == (2, 3)
        assert run.label == "fake"
        assert run.run_at == "2026-11-24T12:00:00+00:00"

    def test_a_failed_model_call_is_a_failed_case_not_a_crash(self, graph, tmp_path):
        from attack_graph.llm import LLMError

        answerer = build(graph, ScriptedLLM(LLMError()), tmp=tmp_path)

        run = run_evals(answerer, [case(question=POWERSHELL_Q)], label="x", now=NOW)

        assert not run.results[0].passed
        assert run.results[0].status == "error"


def make_run(*outcomes: tuple[str, bool], run_at="2026-11-24T12:00:00+00:00") -> EvalRun:
    results = tuple(
        CaseResult(cid, "specific", ok, () if ok else ("expected status answered",), "answered", "a", (), ())
        for cid, ok in outcomes
    )
    return EvalRun(run_at=run_at, label="m", results=results)


class TestSummary:
    def test_shows_score_per_kind_and_each_failure(self):
        run = make_run(("good", True), ("bad", False))

        text = summarize(run)

        assert "1/2" in text
        assert "50%" in text
        assert "specific" in text
        assert "bad: expected status answered" in text

    def test_names_what_changed_since_the_previous_run(self):
        before = make_run(("a", True), ("b", False), ("c", True), run_at="2026-11-23T00:00:00+00:00")
        after = make_run(("a", False), ("b", True), ("c", True))

        text = summarize(after, previous=before)

        assert "2/3 -> 2/3" in text
        assert "Newly failing: a" in text
        assert "Newly passing: b" in text

    def test_empty_run_does_not_divide_by_zero(self):
        assert "0/0" in summarize(make_run())


class TestSavedRuns:
    def test_round_trips_through_a_file(self, tmp_path):
        run = make_run(("a", True), ("b", False))

        path = save_run(run, tmp_path / "results")

        assert path.parent == tmp_path / "results"
        assert latest_run(tmp_path / "results") == run

    def test_latest_is_the_newest_by_time(self, tmp_path):
        old = make_run(("a", True), run_at="2026-11-23T08:00:00+00:00")
        new = make_run(("a", False), run_at="2026-11-24T08:00:00+00:00")
        save_run(new, tmp_path)
        save_run(old, tmp_path)

        assert latest_run(tmp_path) == new

    def test_no_results_yet(self, tmp_path):
        assert latest_run(tmp_path / "missing") is None

    def test_a_corrupt_previous_file_is_reported_not_trusted(self, tmp_path):
        (tmp_path / "20261124T000000.json").write_text("not json")

        with pytest.raises(EvalError):
            latest_run(tmp_path)

    def test_saved_file_holds_no_environment_values(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")

        path = save_run(make_run(("a", True)), tmp_path)

        assert "sk-secret-value" not in path.read_text()


class TestEvalSetFile:
    def test_loads_and_covers_every_kind(self):
        cases = load_cases(CASES_FILE) + injection_cases(CORPUS_FILE)

        assert 15 <= len(cases) <= 30
        assert {c.kind for c in cases} >= {"specific", "vague", "unsupported", "injection"}

    def test_ids_are_unique(self):
        ids = [c.id for c in load_cases(CASES_FILE) + injection_cases(CORPUS_FILE)]

        assert len(ids) == len(set(ids))

    def test_every_case_can_actually_fail(self):
        for c in load_cases(CASES_FILE) + injection_cases(CORPUS_FILE):
            checks = [c.expect_status, c.cited_all, c.cited_any, c.must_contain, c.forbidden]
            assert any(checks), f"{c.id} checks nothing"

    def test_questions_fit_the_service_limit(self):
        from attack_graph.answer import MAX_QUESTION_CHARS

        for c in load_cases(CASES_FILE) + injection_cases(CORPUS_FILE):
            assert 0 < len(c.question) <= MAX_QUESTION_CHARS, c.id

    def test_expected_ids_exist_in_the_bundled_fixture(self, graph):
        for c in load_cases(CASES_FILE):
            for attack_id in (*c.cited_all, *c.cited_any):
                assert graph.technique(attack_id) is not None, f"{c.id}: {attack_id}"

    def test_refusal_cases_expect_not_found(self):
        unsupported = [c for c in load_cases(CASES_FILE) if c.kind == "unsupported"]

        assert len(unsupported) >= 3
        assert all(c.expect_status == "not_found" for c in unsupported)

    def test_injection_cases_reuse_the_corpus_and_attach_to_an_on_topic_question(self):
        corpus = json.loads(CORPUS_FILE.read_text())

        cases = injection_cases(CORPUS_FILE)

        assert [c.id for c in cases] == [f"injection-{item['id']}" for item in corpus]
        assert all(item["text"] in c.question for item, c in zip(corpus, cases))
        assert all("PWNED" in c.forbidden for c in cases)

    def test_missing_corpus_gives_no_injection_cases(self, tmp_path):
        assert injection_cases(tmp_path / "nope.json") == []

    @pytest.mark.parametrize(
        "bad",
        [
            "not json",
            "{}",
            '[{"id": "a", "kind": "specific", "question": "q"}, {"id": "a", "kind": "specific", "question": "q"}]',
            '[{"id": "a", "kind": "weird", "question": "q", "expect_status": "answered"}]',
            '[{"id": "a", "kind": "specific", "question": "", "expect_status": "answered"}]',
            '[{"id": "a", "kind": "specific", "question": "q", "expect_status": "maybe"}]',
            '[{"id": "a", "kind": "specific", "question": "q", "expect_status": "answered", "extra": 1}]',
        ],
    )
    def test_bad_files_are_rejected_with_a_clear_error(self, tmp_path, bad):
        path = tmp_path / "cases.json"
        path.write_text(bad)

        with pytest.raises(EvalError):
            load_cases(path)

    def test_missing_file_is_a_clear_error(self, tmp_path):
        with pytest.raises(EvalError):
            load_cases(tmp_path / "nope.json")


class TestEvalsStayOutOfTheNormalRun:
    def test_pytest_only_collects_the_tests_folder(self):
        import tomllib

        config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]

        assert config["testpaths"] == ["tests"]
        assert not (ROOT / "evals").samefile(ROOT / "tests")
        assert list((ROOT / "evals").glob("test_*.py")) == []
        assert list((ROOT / "evals").glob("*_test.py")) == []
