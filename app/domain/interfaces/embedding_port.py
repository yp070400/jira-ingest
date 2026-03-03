"""Abstract embedding port."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class EmbeddingPort(ABC):
    """Port (interface) for embedding model adapters."""

    @abstractmethod
    async def embed_text(self, text: str) -> np.ndarray:
        """Generate a normalized embedding vector for a single text."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Generate embeddings for a batch of texts."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the embedding service is available."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the embedding model identifier."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding vector dimension."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Return a version string for cache-key and migration tracking."""