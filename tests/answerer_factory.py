"""Shared test setup: build an Answerer over a graph, an offline embedder and a throwaway Chroma folder."""

from attack_graph.answer import Answerer
from attack_graph.vector import ChromaVectorStore
from fake_embedder import fake_word_embed


def build(graph, llm, embed=fake_word_embed, tmp=None):
    store = ChromaVectorStore(tmp, embed=embed)
    store.index(graph.technique_docs())
    return Answerer(vectors=store, graph=graph, llm=llm)
