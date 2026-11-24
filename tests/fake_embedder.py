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
