from attack_graph.cli import main
from fake_embedder import fake_embed


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv), embed=fake_embed)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestIndexAndSearch:
    def test_index_then_search_prints_closest_techniques(self, capsys):
        assert run(capsys, "index")[0] == 0

        code, out, _ = run(capsys, "search", "use PowerShell to run commands and scripts on Windows")

        assert code == 0
        assert out.splitlines()[0].startswith("T1059.001 PowerShell")

    def test_limit_caps_the_number_of_results(self, capsys):
        run(capsys, "index")

        code, out, _ = run(capsys, "search", "--limit", "2", "credentials")

        assert code == 0
        assert len(out.strip().splitlines()) == 2

    def test_index_twice_is_safe(self, capsys):
        run(capsys, "index")
        first = run(capsys, "search", "--limit", "20", "email")[1]

        assert run(capsys, "index")[0] == 0
        assert run(capsys, "search", "--limit", "20", "email")[1] == first

    def test_search_before_index_says_to_run_index(self, capsys):
        code, out, err = run(capsys, "search", "email")

        assert code == 2
        assert out == ""
        assert "attack-graph index" in err

    def test_blank_question_gives_clear_message(self, capsys):
        run(capsys, "index")

        code, _, err = run(capsys, "search", "  ")

        assert code == 2
        assert "empty" in err
