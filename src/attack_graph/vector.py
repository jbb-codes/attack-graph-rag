"""Search ATT&CK techniques by meaning, using Chroma.

An embedding turns text into a list of numbers so that texts with similar
meaning get similar numbers. Searching means embedding the question and
asking Chroma for the techniques whose numbers are closest.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import chromadb

from attack_graph.graph import TechniqueDoc

Embed = Callable[[Sequence[str]], list[list[float]]]

_COLLECTION = "techniques"


class VectorStoreError(Exception):
    """The search could not run, e.g. nothing is indexed yet or the question is blank."""


@dataclass(frozen=True)
class Hit:
    attack_id: str
    name: str
    distance: float  # smaller means closer in meaning


class VectorStore(Protocol):
    """All the rest of the app needs to know about vector search."""

    def index(self, techniques: Sequence[TechniqueDoc]) -> None: ...

    def search(self, question: str, limit: int = 5) -> list[Hit]: ...


def default_embed(texts: Sequence[str]) -> list[list[float]]:
    # Chroma's bundled all-MiniLM-L6-v2 model; downloaded once, then cached.
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    return [list(map(float, v)) for v in DefaultEmbeddingFunction()(list(texts))]


class ChromaVectorStore:
    def __init__(self, path: Path | str, embed: Embed = default_embed) -> None:
        self._client = chromadb.PersistentClient(path=str(Path(path).resolve()))  # Chroma caches clients by path text, so relative paths can collide
        self._embed = embed

    def index(self, techniques: Sequence[TechniqueDoc]) -> None:
        # Rebuilt from scratch, like the graph load: no duplicates, and
        # techniques removed from the data cannot linger in search results.
        self._drop()
        if not techniques:
            return
        collection = self._client.create_collection(_COLLECTION, configuration={"hnsw": {"space": "cosine"}})
        texts = [f"{t.name}. {t.description}" for t in techniques]
        collection.add(
            ids=[t.attack_id for t in techniques],
            documents=texts,
            embeddings=self._embed(texts),
            metadatas=[{"name": t.name} for t in techniques],
        )

    def search(self, question: str, limit: int = 5) -> list[Hit]:
        if not question.strip():
            raise VectorStoreError("The question is empty.")
        if limit < 1:
            raise VectorStoreError("The limit must be at least 1.")
        try:
            collection = self._client.get_collection(_COLLECTION)
        except Exception as exc:  # chromadb raises different types by version
            raise VectorStoreError("Nothing is indexed yet; run 'attack-graph index' first.") from exc
        result = collection.query(
            query_embeddings=self._embed([question]),
            n_results=min(limit, collection.count()),
        )
        return [
            Hit(attack_id=id_, name=meta["name"], distance=float(dist))
            for id_, meta, dist in zip(
                result["ids"][0], result["metadatas"][0], result["distances"][0], strict=True
            )
        ]

    def _drop(self) -> None:
        try:
            self._client.delete_collection(_COLLECTION)
        except Exception:  # first run: nothing to delete
            pass
