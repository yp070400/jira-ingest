"""Vector search and reranking service."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import numpy as np

from app.application.dto.analysis_dto import SimilarTicketDTO
from app.config import get_settings
from app.domain.interfaces.vector_store_port import SearchResult, VectorStorePort
from app.domain.value_objects.score import ConfidenceScore, SimilarityScore
from app.observability.metrics import (
    vector_search_duration_seconds,
    vector_search_results_count,
    track_async_duration,
)

if TYPE_CHECKING:
    from app.repositories.ticket_repository import TicketRepository
    from app.repositories.reranking_repository import RerankingRepository

logger = logging.getLogger(__name__)


class SearchService:
    """Orchestrates FAISS search, metadata enrichment, and reranking."""

    def __init__(
        self,
        vector_store: VectorStorePort,
        ticket_repo: "TicketRepository",
        reranking_repo: "RerankingRepository",
    ) -> None:
        self._vector_store = vector_store
        self._ticket_repo = ticket_repo
        self._reranking_repo = reranking_repo
        self._settings = get_settings()

    async def search_similar(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        project_key: str | None = None,
    ) -> list[SimilarTicketDTO]:
        """Search FAISS, enrich with DB metadata, apply reranking."""
        async with track_async_duration(vector_search_duration_seconds):
            raw_results = await self._vector_store.search(
                query_vector=query_vector,
                top_k=top_k * 2,  # Over-fetch for post-filtering
                similarity_threshold=self._settings.faiss_similarity_threshold,
            )

        vector_search_results_count.observe(len(raw_results))

        if not raw_results:
            return []

        # Fetch ticket details from DB
        ticket_ids = [r.ticket_id for r in raw_results]
        tickets = await self._ticket_repo.get_by_ids(ticket_ids)
        ticket_map = {t.id: t for t in tickets}

        # Load reranking weights
        weights = await self._reranking_repo.get_all_weights()
        w_sim = weights.get("similarity", self._settings.reranking_similarity_weight)
        w_rec = weights.get("recency", self._settings.reranking_recency_weight)
        w_fb = weights.get("feedback", self._settings.reranking_feedback_weight)
        w_qual = weights.get("quality", self._settings.reranking_quality_weight)

        now = datetime.now(timezone.utc)
        scored: list[tuple[float, SearchResult]] = []

        for result in raw_results:
            ticket = ticket_map.get(result.ticket_id)
            if not ticket:
                continue
            if project_key and ticket.project_key != project_key:
                continue

            # Recency score: newer = higher, max 1.0
            recency_score = 0.5
            if ticket.resolved_at:
                resolved = ticket.resolved_at
                if resolved.tzinfo is None:
                    resolved = resolved.replace(tzinfo=timezone.utc)
                days_old = (now - resolved).days
                recency_score = math.exp(-0.005 * days_old)  # decay over ~200 days

            final_score = (
                w_sim * result.similarity_score
                + w_rec * recency_score
                + w_qual * ticket.quality_score
            )
            scored.append((final_score, result))

        # Sort by reranked score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[SimilarTicketDTO] = []
        for rank_score, raw in scored[:top_k]:
            ticket = ticket_map[raw.ticket_id]
            confidence = self._calibrate_confidence(raw.similarity_score, rank_score)

            results.append(
                SimilarTicketDTO(
                    jira_id=ticket.jira_id,
                    ticket_db_id=ticket.id,
                    summary=ticket.summary,
                    resolution=ticket.resolution,
                    similarity_score=round(raw.similarity_score, 4),
                    confidence_score=round(confidence, 4),
                    project_key=ticket.project_key,
                    priority=ticket.priority,
                    resolved_at=ticket.resolved_at,
                    labels=ticket.labels or [],
                    components=ticket.components or [],
                    quality_score=ticket.quality_score,
                )
            )

        return results

    def _calibrate_confidence(self, similarity: float, rerank_score: float) -> float:
        """
        Sigmoid-calibrated confidence score.
        Combines raw similarity with reranked score.
        """
        combined = (similarity * 0.7) + (rerank_score * 0.3)
        # Sigmoid: maps combined score to [0, 1] with inflection at 0.5
        sigmoid = 1.0 / (1.0 + math.exp(-10.0 * (combined - 0.5)))
        return min(1.0, max(0.0, sigmoid))

    def detect_novel_pattern(self, search_results: list[SimilarTicketDTO]) -> bool:
        """Return True if the query doesn't match any known pattern well."""
        if not search_results:
            return True
        best_score = search_results[0].similarity_score
        return best_score < self._settings.novelty_threshold