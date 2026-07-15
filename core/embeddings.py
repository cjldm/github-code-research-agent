"""Local hash-based embeddings for offline code RAG (no API key needed)."""
from __future__ import annotations

import hashlib
import re

from langchain_core.embeddings import Embeddings


class LocalHashEmbeddings(Embeddings):
    """Deterministic embeddings using blake2b hashing. No API key required."""

    def __init__(self, dimensions: int = 1024):
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[一-鿿]{1,}", text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = sum(v * v for v in vector) ** 0.5 or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def __call__(self, text: str) -> list[float]:
        return self.embed_query(text)
