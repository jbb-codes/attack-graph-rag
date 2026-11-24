from importlib.resources import as_file, files

import pytest

from attack_graph.graph import AttackGraph, TechniqueDoc
from attack_graph.vector import ChromaVectorStore, VectorStoreError
from fake_embedder import fake_embed


def docs(*pairs: tuple[str, str, str]) -> list[TechniqueDoc]:
    return [TechniqueDoc(*pair) for pair in pairs]


def fixture_docs() -> tuple[TechniqueDoc, ...]:
    with as_file(files("attack_graph") / "data" / "attack_fixture.json") as path:
        return AttackGraph.from_stix_file(path).technique_docs()


@pytest.fixture
def store(tmp_path):
    return ChromaVectorStore(tmp_path / "chroma", embed=fake_embed)


class TestIdempotentIndex:
    def test_indexing_twice_gives_same_results_as_once(self, store):
        technique_docs = fixture_docs()

        store.index(technique_docs)
        once = store.search("targeted emails with a malicious attachment", limit=20)
        store.index(technique_docs)
        twice = store.search("targeted emails with a malicious attachment", limit=20)

        assert once == twice
        assert len(twice) == len(technique_docs)

    def test_reindexing_drops_techniques_that_disappeared(self, store):
        store.index(docs(("T1", "Alpha", "red apples"), ("T2", "Beta", "green pears")))
        store.index(docs(("T1", "Alpha", "red apples")))

        ids = [hit.attack_id for hit in store.search("green pears", limit=10)]

        assert ids == ["T1"]

    def test_reindexing_picks_up_changed_text(self, store):
        store.index(docs(("T1", "Alpha", "red apples"), ("T2", "Beta", "green pears")))
        store.index(docs(("T1", "Alpha", "green pears"), ("T2", "Beta", "red apples")))

        top = store.search("green pears", limit=1)[0]

        assert top.attack_id == "T1"

    def test_index_persists_across_store_instances(self, tmp_path):
        ChromaVectorStore(tmp_path / "c", embed=fake_embed).index(fixture_docs())

        reopened = ChromaVectorStore(tmp_path / "c", embed=fake_embed)

        assert reopened.search("PowerShell scripts", limit=1)[0].attack_id == "T1059.001"


class TestSearch:
    def test_returns_closest_first_with_name_and_limit(self, store):
        store.index(fixture_docs())

        hits = store.search("use PowerShell to run commands and scripts on Windows", limit=3)

        assert len(hits) == 3
        assert hits[0].attack_id == "T1059.001"
        assert hits[0].name == "PowerShell"
        assert hits[0].distance <= hits[1].distance <= hits[2].distance

    def test_limit_larger_than_store_returns_everything(self, store):
        store.index(docs(("T1", "Alpha", "red apples")))

        assert len(store.search("apples", limit=50)) == 1

    def test_search_before_index_says_to_index_first(self, store):
        with pytest.raises(VectorStoreError, match="index"):
            store.search("anything")

    @pytest.mark.parametrize("question", ["", "   "])
    def test_blank_question_is_rejected(self, store, question):
        store.index(fixture_docs())

        with pytest.raises(VectorStoreError, match="empty"):
            store.search(question)

    def test_non_positive_limit_is_rejected(self, store):
        store.index(fixture_docs())

        with pytest.raises(VectorStoreError, match="limit"):
            store.search("phishing", limit=0)


@pytest.fixture(scope="module")
def real_store(tmp_path_factory):
    store = ChromaVectorStore(tmp_path_factory.mktemp("real") / "chroma")
    store.index(fixture_docs())
    return store


@pytest.mark.model
class TestSearchByMeaning:
    """Uses the real embedding model (one-time ~80 MB download, then cached)."""

    def test_vague_email_question_finds_phishing_techniques(self, real_store):
        hits = real_store.search("how do attackers sneak in through email?", limit=3)

        ids = {hit.attack_id for hit in hits}
        assert ids & {"T1566", "T1566.001"}

    def test_vague_ransom_question_finds_encryption_for_impact(self, real_store):
        hits = real_store.search("criminals lock my files and demand payment", limit=3)

        assert "T1486" in {hit.attack_id for hit in hits}
