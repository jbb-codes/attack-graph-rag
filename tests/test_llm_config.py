"""Provider choice and startup validation, seen from the `ask` command."""

from attack_graph.cli import main
from fake_embedder import fake_word_embed

QUESTION = "Which techniques use PowerShell to run commands and scripts on Windows?"


def run(capsys, *argv: str, env: dict[str, str]) -> tuple[int, str, str]:
    code = main(list(argv), embed=fake_word_embed, env=env)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_offline_provider_answers_without_any_key(capsys):
    run(capsys, "index", env={})

    code, out, _ = run(capsys, "ask", QUESTION, env={"ATTACK_GRAPH_LLM": "offline"})

    assert code == 0
    assert "[T1059.001]" in out


def test_claude_is_the_default_and_needs_an_api_key(capsys):
    run(capsys, "index", env={})

    code, out, err = run(capsys, "ask", QUESTION, env={})

    assert code == 2
    assert "ANTHROPIC_API_KEY" in err
    assert out == ""


def test_blank_api_key_counts_as_missing(capsys):
    code, _, err = run(capsys, "ask", QUESTION, env={"ANTHROPIC_API_KEY": "   "})

    assert code == 2
    assert "ANTHROPIC_API_KEY" in err


def test_local_provider_needs_a_model_name(capsys):
    code, _, err = run(capsys, "ask", QUESTION, env={"ATTACK_GRAPH_LLM": "local"})

    assert code == 2
    assert "ATTACK_GRAPH_LOCAL_MODEL" in err


def test_unknown_provider_lists_the_valid_ones(capsys):
    code, _, err = run(capsys, "ask", QUESTION, env={"ATTACK_GRAPH_LLM": "gpt"})

    assert code == 2
    assert "claude" in err and "local" in err and "offline" in err


def test_config_is_checked_before_the_index_is_touched(capsys):
    # No index exists here: a config error must win over the "run index" error.
    code, _, err = run(capsys, "ask", QUESTION, env={})

    assert "ANTHROPIC_API_KEY" in err
    assert "attack-graph index" not in err


def test_error_message_never_echoes_the_key(capsys):
    secret = "sk-ant-test-secret-value"

    _, out, err = run(capsys, "ask", QUESTION, env={"ATTACK_GRAPH_LLM": "bogus", "ANTHROPIC_API_KEY": secret})

    assert secret not in out + err


def test_commands_that_need_no_llm_ignore_llm_config(capsys):
    code, _, _ = run(capsys, "technique", "T1059.001", env={"ATTACK_GRAPH_LLM": "bogus"})

    assert code == 0
