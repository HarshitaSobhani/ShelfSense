"""Embedding providers. Semantic search is only reported as active when a real model is loaded."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.config import get_settings

log = logging.getLogger("shelfsense.embeddings")

SETUP_HELP = (
    "Install the optional embedding dependencies (`pip install -e '.[embeddings]'`) and download the model "
    "once with `python -m app.cli download-model` (needs internet access to huggingface.co). "
    "Then run `python -m app.cli rebuild-index`. See docs/MODEL_SETUP.md."
)


class Embedder(Protocol):
    name: str
    revision: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class EmbeddingUnavailable(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class EmbedderStatus:
    available: bool
    model: str
    reason: str | None = None
    setup: str | None = None


class SentenceTransformerEmbedder:
    def __init__(self, name: str, revision: str, dim: int):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover - depends on environment
            raise EmbeddingUnavailable("sentence-transformers is not installed") from e
        try:
            rev = None if revision in ("", "main") else revision
            self._model = SentenceTransformer(name, revision=rev)
        except Exception as e:  # network failure, missing cache, bad name
            raise EmbeddingUnavailable(f"could not load model '{name}': {type(e).__name__}: {e}") from e
        self.name, self.revision = name, revision
        actual = self._model.get_embedding_dimension()
        if actual != dim:
            raise EmbeddingUnavailable(f"model produces {actual}-dim vectors but SHELFSENSE_EMBEDDING_DIM={dim}")
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = self._model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        return np.asarray(out, dtype=np.float32)


_lock = threading.Lock()
_embedder: Embedder | None = None
_failure: str | None = None
_override: Embedder | None = None


def set_embedder_override(e: Embedder | None) -> None:
    """Tests inject controlled embedders here."""
    global _override
    _override = e


def reset_embedder() -> None:
    global _embedder, _failure
    with _lock:
        _embedder, _failure = None, None


def get_embedder() -> Embedder | None:
    global _embedder, _failure
    if _override is not None:
        return _override
    if _embedder is not None:
        return _embedder
    s = get_settings()
    if s.embedding_provider == "none":
        _failure = "embedding provider disabled (SHELFSENSE_EMBEDDING_PROVIDER=none)"
        return None
    with _lock:
        if _embedder is None and _failure is None:
            try:
                _embedder = SentenceTransformerEmbedder(s.embedding_model, s.embedding_model_revision, s.embedding_dim)
            except EmbeddingUnavailable as e:
                _failure = e.reason
                log.warning("Embeddings unavailable: %s", e.reason)
    return _embedder


def embedder_status() -> EmbedderStatus:
    s = get_settings()
    e = get_embedder()
    if e is not None:
        return EmbedderStatus(True, e.name)
    return EmbedderStatus(False, s.embedding_model, _failure or "unknown", SETUP_HELP)
