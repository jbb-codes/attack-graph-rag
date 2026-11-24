import pytest

from attack_graph.cli import main


@pytest.mark.parametrize("name", ["ATTACK_GRAPH_SPARQL_URL", "ATTACK_GRAPH_CHROMA_URL"])
@pytest.mark.parametrize("bad", ["not a url", "ftp://host", "http://", "http://user:secret@host:1", "http://host:notaport"])
def test_bad_store_address_is_rejected_by_name_without_echoing_it(capsys, name, bad):
    code = main(["technique", "T1566"], env={name: bad})

    err = capsys.readouterr().err
    assert code == 2
    assert name in err
    assert "secret" not in err


def test_unreachable_chroma_server_fails_search_cleanly(capsys):
    code = main(["search", "email"], env={"ATTACK_GRAPH_CHROMA_URL": "http://127.0.0.1:9"})

    assert code == 2
    assert "Traceback" not in capsys.readouterr().err
