"""Tiny offline embedder for tests that don't need real meaning.

Hashes each word into one of 64 buckets and counts them, so texts that
share words land close together. No model download, fully deterministic.
"""

import hashlib
import math
from collections.abc import Sequence

DIMENSIONS = 64


def fake_embed(texts: Sequence[str]) -> list[list[float]]:
    return [_embed_one(text) for text in texts]


def _embed_one(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for word in text.lower().split():
        bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIMENSIONS
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


_STOPWORDS = frozenset(
    "a an and are as at be by do does for from how in is it of on or that the this to use what which with".split()
)
_WORD_BUCKETS = 4096


def fake_word_embed(texts: Sequence[str]) -> list[list[float]]:
    """Like fake_embed, but ignores filler words and rarely collides.

    Texts that share no meaningful word are exactly unrelated (distance 1.0),
    so "nothing relevant found" can be tested without a real model.
    """
    return [_embed_words(text) for text in texts]


def _embed_words(text: str) -> list[float]:
    vector = [0.0] * _WORD_BUCKETS
    for raw in text.lower().split():
        word = raw.strip(".,;:!?\"'()[]")
        if not word or word in _STOPWORDS:
            continue
        vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % _WORD_BUCKETS] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
