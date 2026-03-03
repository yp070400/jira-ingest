"""Embedding generation and management service."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np

from app.domain.exceptions.domain_exceptions import EmbeddingGenerationError
from app.domain.interfaces.embedding_port import EmbeddingPort
from app.domain.interfaces.vector_store_port import VectorStorePort
from app.observability.metrics import (
    embedding_generation_duration_seconds,
    total_indexed_tickets,
    track_async_duration,
)

if TYPE_CHECKING:
    from app.repositories.embedding_repository import EmbeddingRepository
    from app.repositories.ticket_repository import TicketRepository

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Orchestrates embedding generation, storage, and index management."""

    def __init__(
        self,
        embedding_adapter: EmbeddingPort,
        vector_store: VectorStorePort,
        embedding_repo: "EmbeddingRepository",
        ticket_repo: "TicketRepository",
    ) -> None:
        self._embedding = embedding_adapter
        self._vector_store = vector_store
        self._embedding_repo = embedding_repo
        self._ticket_repo = ticket_repo

    @property
    def current_version(self) -> str:
        return self._embedding.version

    async def embed_and_index_ticket(self, ticket_db_id: str) -> int | None:
        """Generate embedding for a ticket and add it to FAISS. Returns faiss_id."""
        ticket = await self._ticket_repo.get_by_id(ticket_db_id)
        if not ticket:
            logger.warning("Ticket %s not found for embedding", ticket_db_id)
            return None

        text = self._build_embedding_text(ticket)

        async with track_async_duration(embedding_generation_duration_seconds):
            try:
                vector = await self._embedding.embed_text(text)
            except Exception as e:
                raise EmbeddingGenerationError(str(e)) from e

        vector_hash = hashlib.sha256(vector.tobytes()).hexdigest()

        # Check for existing embedding with same hash (dedup)
        existing = await self._embedding_repo.get_by_ticket_id(ticket_db_id)
        if existing and existing.embedding_hash == vector_hash:
            if self._vector_store.has_ticket(ticket_db_id):
                # Vector is already in FAISS and DB — truly nothing to do
                logger.debug("Skipping duplicate embedding for ticket %s", ticket_db_id)
                await self._ticket_repo.mark_as_indexed(ticket_db_id, self.current_version)
                return existing.faiss_index_id
            # DB record exists but vector is missing from FAISS (e.g. after restart or
            # fresh volume).  Re-add it without touching the DB embedding record.
            logger.debug(
                "Re-adding ticket %s to FAISS (vector was missing from index)", ticket_db_id
            )

        faiss_id = await self._vector_store.add_vector(ticket_db_id, vector)

        embedding_data = {
            "ticket_id": ticket_db_id,
            "vector_version": self.current_version,
            "model_name": self._embedding.model_name,
            "embedding_dimension": self._embedding.dimension,
            "embedding_hash": vector_hash,
            "faiss_index_id": faiss_id,
        }
        await self._embedding_repo.upsert_embedding(embedding_data)
        await self._ticket_repo.mark_as_indexed(ticket_db_id, self.current_version)

        total_indexed_tickets.set(self._vector_store.count())
        logger.debug(
            "Indexed ticket %s -> faiss_id=%d version=%s",
            ticket_db_id, faiss_id, self.current_version,
        )
        return faiss_id

    async def embed_batch(self, ticket_db_ids: list[str]) -> dict[str, int | None]:
        """Process a batch of tickets for embedding. Returns {ticket_id: faiss_id}."""
        results: dict[str, int | None] = {}
        for ticket_id in ticket_db_ids:
            try:
                faiss_id = await self.embed_and_index_ticket(ticket_id)
                results[ticket_id] = faiss_id
            except Exception as e:
                logger.error("Failed to embed ticket %s: %s", ticket_id, e)
                results[ticket_id] = None
        await self._vector_store.persist()
        return results

    async def embed_query(self, text: str) -> np.ndarray:
        """Generate an embedding for a search query."""
        async with track_async_duration(embedding_generation_duration_seconds):
            return await self._embedding.embed_text(text)

    async def reindex_all(self) -> int:
        """Rebuild the entire FAISS index from scratch."""
        logger.info("Starting full reindex...")
        unindexed = await self._ticket_repo.get_unindexed(limit=10000)

        pairs: list[tuple[str, np.ndarray]] = []
        for ticket in unindexed:
            text = self._build_embedding_text(ticket)
            try:
                vector = await self._embedding.embed_text(text)
                pairs.append((ticket.id, vector))
            except Exception as e:
                logger.error("Reindex: failed to embed ticket %s: %s", ticket.id, e)

        await self._vector_store.rebuild_index(pairs)

        # Update all embedding records
        for ticket in unindexed:
            if ticket.id in {p[0] for p in pairs}:
                await self._ticket_repo.mark_as_indexed(ticket.id, self.current_version)

        total_indexed_tickets.set(self._vector_store.count())
        logger.info("Reindex complete: %d tickets indexed", len(pairs))
        return len(pairs)

    async def get_embedding_health(self) -> dict:
        """Check embedding pipeline health and detect stale embeddings."""
        stale = await self._ticket_repo.get_tickets_needing_reindex(self.current_version)
        unindexed = await self._ticket_repo.get_unindexed()
        return {
            "current_version": self.current_version,
            "model_name": self._embedding.model_name,
            "dimension": self._embedding.dimension,
            "total_indexed": self._vector_store.count(),
            "stale_count": len(stale),
            "unindexed_count": len(unindexed),
            "adapter_healthy": await self._embedding.health_check(),
        }

    @staticmethod
    def _build_embedding_text(ticket) -> str:
        """Build the text representation for embedding from an ORM model."""
        parts = [f"Summary: {ticket.summary}"]
        if ticket.description:
            parts.append(f"Description: {ticket.description[:3000]}")
        if ticket.resolution:
            parts.append(f"Resolution: {ticket.resolution[:2000]}")
        labels = ticket.labels or []
        if labels:
            parts.append(f"Labels: {', '.join(labels)}")
        components = ticket.components or []
        if components:
            parts.append(f"Components: {', '.join(components)}")
        return "\n\n".join(parts)