"""Abstract vector store port."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class SearchResult:
    ticket_id: str
    faiss_index_id: int
    similarity_score: float
    distance: float


class VectorStorePort(ABC):
    """Port (interface) for vector store adapters."""

    @abstractmethod
    async def add_vector(self, ticket_id: str, vector: np.ndarray) -> int:
        """Add a vector and return its FAISS index ID."""

    @abstractmethod
    async def update_vector(self, faiss_index_id: int, vector: np.ndarray) -> None:
        """Update an existing vector by its FAISS index ID."""

    @abstractmethod
    async def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        similarity_threshold: float = 0.0,
    ) -> list[SearchResult]:
        """Search for the most similar vectors."""

    @abstractmethod
    async def delete_vector(self, faiss_index_id: int) -> None:
        """Soft-delete a vector (mark as removed)."""

    @abstractmethod
    async def persist(self) -> None:
        """Flush the in-memory index to disk."""

    @abstractmethod
    async def load(self) -> None:
        """Load the persisted index from disk."""

    @abstractmethod
    def count(self) -> int:
        """Return the number of vectors currently indexed."""

    @abstractmethod
    def has_ticket(self, ticket_id: str) -> bool:
        """Return True if the given ticket_id has a vector in the store."""

    @abstractmethod
    async def rebuild_index(self, vectors: list[tuple[str, np.ndarray]]) -> None:
        """Rebuild the entire index from scratch."""