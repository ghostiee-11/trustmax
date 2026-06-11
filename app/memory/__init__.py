"""Embeddings + vector search utilities (open, local).

fastembed (ONNX) when available, with a deterministic char-n-gram fallback so everything runs with no
heavy dependencies. Used by GraphRAG retrieval (cold-vendor fallback) and entity resolution.
"""
from __future__ import annotations

import numpy as np

from .. import config

_DIM_FALLBACK = 512


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return v / n


class _FastEmbedder:
    backend = "fastembed"

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name=model_name)
        vec = next(iter(self._model.embed(["probe"])))
        self.dim = int(np.asarray(vec).shape[0])

    def embed(self, texts: list[str]) -> np.ndarray:
        arr = np.array(list(self._model.embed(list(texts))), dtype="float32")
        return _normalize(arr)


class _HashEmbedder:
    backend = "hash-ngram"
    dim = _DIM_FALLBACK

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for i, t in enumerate(texts):
            s = f"  {t.lower()} "
            for j in range(len(s) - 2):
                out[i, hash(s[j:j + 3]) % self.dim] += 1.0
        return _normalize(out)


_EMBEDDER = None


def get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        if config.EMBED_BACKEND == "hash":
            _EMBEDDER = _HashEmbedder()
        else:
            try:
                _EMBEDDER = _FastEmbedder(config.EMBED_MODEL)
            except Exception as e:  # pragma: no cover
                print(f"[memory] fastembed unavailable ({e}); using hash-ngram fallback")
                _EMBEDDER = _HashEmbedder()
    return _EMBEDDER


class VectorIndex:
    """Small FAISS inner-product index over normalized vectors (cosine)."""

    def __init__(self, dim: int):
        import faiss
        self.dim = dim
        self._index = faiss.IndexFlatIP(dim)
        self._metas: list[dict] = []

    def add(self, vectors: np.ndarray, metas: list[dict]) -> None:
        if len(metas) == 0:
            return
        self._index.add(vectors.astype("float32"))
        self._metas.extend(metas)

    def search(self, query: np.ndarray, k: int = 5) -> list[tuple[dict, float]]:
        if len(self._metas) == 0:
            return []
        k = min(k, len(self._metas))
        sims, idxs = self._index.search(query.astype("float32"), k)
        out = []
        for sim, idx in zip(sims[0], idxs[0]):
            if idx >= 0:
                out.append((self._metas[idx], float(sim)))
        return out

    def __len__(self) -> int:
        return len(self._metas)
