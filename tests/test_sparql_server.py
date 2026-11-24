"""The graph can live in a separate SPARQL server instead of memory (used by Docker Compose)."""

import hashlib
from importlib.resources import files

import pytest

from attack_graph.cli import main
from attack_graph.release import Release
from fake_sparql_server import sparql_server

BUNDLE = (files("attack_graph") / "data" / "attack_fixture.json").read_bytes()
RELEASE = Release("0.0-test", "https://example.invalid/b.json", hashlib.sha256(BUNDLE).hexdigest())


def run(capsys, *argv: str, url: str | None = None):
    env = {"ATTACK_GRAPH_SPARQL_URL": url} if url else {}
    code = main(list(argv), fetch=lambda _: BUNDLE, release=RELEASE, env=env)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def server():
    with sparql_server() as s:
        yield s


def test_lookups_after_load_come_from_the_server_and_match_local_results(capsys, server):
    assert run(capsys, "load", url=server.url)[0] == 0

    for lookup in (("technique", "T1566.001"), ("group", "APT29")):
        remote = run(capsys, *lookup, url=server.url)
        local = run(capsys, *lookup)  # no URL: the bundled fixture, held in memory
        assert remote[0] == 0
        assert remote == local


def test_load_keeps_no_local_graph_file_when_a_server_is_configured(capsys, server, tmp_path):
    run(capsys, "load", url=server.url)

    assert not (tmp_path / "data" / "attack-graph.nt").exists()


def test_loading_twice_does_not_duplicate_facts(capsys, server):
    run(capsys, "load", url=server.url)
    first = len(server.graph)

    run(capsys, "load", url=server.url)

    assert len(server.graph) == first > 0


def test_quotes_in_a_lookup_cannot_change_the_query(capsys, server):
    run(capsys, "load", url=server.url)

    code, _, err = run(capsys, "group", 'x" } UNION { ?s ?p ?o', url=server.url)

    assert code == 1
    assert "No group found" in err


def test_unreachable_server_gives_a_clear_error_without_a_traceback(capsys):
    code, _, err = run(capsys, "technique", "T1566", url="http://127.0.0.1:9")

    assert code == 2
    assert "ATTACK_GRAPH_SPARQL_URL" in err
    assert "Traceback" not in err


def test_server_error_on_load_is_reported_not_raised(capsys, server):
    server.fail_with = 500

    code, _, err = run(capsys, "load", url=server.url)

    assert code == 2
    assert "SPARQL server" in err


@pytest.mark.parametrize("bad", ["not a url", "ftp://host/x", "http://"])
def test_invalid_server_url_is_rejected_naming_the_variable(capsys, bad):
    code, _, err = run(capsys, "technique", "T1566", url=bad)

    assert code == 2
    assert "ATTACK_GRAPH_SPARQL_URL" in err
