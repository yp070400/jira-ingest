"""Core analysis orchestration service."""
from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

from app.application.dto.analysis_dto import (
    AnalysisMode,
    DeepAnalysisResponse,
    QuickAnalysisResponse,
    SimilarTicketDTO,
)
from app.config import get_settings
from app.domain.interfaces.llm_port import LLMPort
from app.domain.value_objects.score import ConfidenceScore
from app.observability.metrics import (
    analysis_cache_hits_total,
    analysis_requests_total,
    confidence_score_histogram,
    llm_request_duration_seconds,
    llm_tokens_used_total,
    review_flags_total,
    track_async_duration,
)

if TYPE_CHECKING:
    from app.application.services.embedding_service import EmbeddingService
    from app.application.services.search_service import SearchService
    from app.domain.interfaces.cache_port import CachePort
    from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "analysis"


def _cache_key(text: str, mode: str) -> str:
    digest = hashlib.sha256(f"{mode}:{text}".encode()).hexdigest()[:16]
    return f"{_CACHE_PREFIX}:{mode}:{digest}"


class AnalysisService:
    """Orchestrates the full analysis pipeline: embed -> search -> rerank -> LLM."""

    def __init__(
        self,
        embedding_service: "EmbeddingService",
        search_service: "SearchService",
        llm_adapter: LLMPort,
        cache: "CachePort",
        audit_repo: "AuditRepository",
    ) -> None:
        self._embedding = embedding_service
        self._search = search_service
        self._llm = llm_adapter
        self._cache = cache
        self._audit = audit_repo
        self._settings = get_settings()

    async def analyze(
        self,
        text: str,
        mode: AnalysisMode,
        jira_id: str | None = None,
        project_key: str | None = None,
        user_id: str | None = None,
        ip_address: str | None = None,
    ) -> QuickAnalysisResponse | DeepAnalysisResponse:
        start_time = time.perf_counter()
        analysis_requests_total.labels(mode=mode.value).inc()

        if mode == AnalysisMode.QUICK:
            result = await self._quick_analyze(
                text, jira_id, project_key, user_id, ip_address, start_time
            )
        else:
            result = await self._deep_analyze(
                text, jira_id, project_key, user_id, ip_address, start_time
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        result.processing_time_ms = round(elapsed_ms, 2)

        confidence_score_histogram.labels(mode=mode.value).observe(result.confidence_score)

        await self._audit.log(
            action=f"analyze:{mode.value}",
            user_id=user_id,
            details={
                "jira_id": jira_id,
                "confidence": result.confidence_score,
                "requires_review": result.requires_human_review,
                "processing_ms": elapsed_ms,
            },
            ip_address=ip_address,
        )

        return result

    async def _quick_analyze(
        self,
        text: str,
        jira_id: str | None,
        project_key: str | None,
        user_id: str | None,
        ip_address: str | None,
        start_time: float,
    ) -> QuickAnalysisResponse:
        # Cache check
        cache_key = _cache_key(text, "quick")
        cached = await self._cache.get(cache_key)
        if cached:
            analysis_cache_hits_total.labels(mode="quick").inc()
            response = QuickAnalysisResponse(**cached)
            response.cache_hit = True
            return response

        # Generate embedding
        query_vector = await self._embedding.embed_query(text)

        # Search similar tickets
        similar_tickets = await self._search.search_similar(
            query_vector,
            top_k=self._settings.quick_analysis_top_k,
            project_key=project_key,
        )

        top_similarity = similar_tickets[0].similarity_score if similar_tickets else 0.0
        top_confidence = similar_tickets[0].confidence_score if similar_tickets else 0.0
        confidence = ConfidenceScore(top_confidence)

        # Detect review conditions
        review_reasons = self._check_review_conditions(
            text, confidence.value, similar_tickets
        )

        # Generate LLM summary
        similar_dicts = [t.model_dump() for t in similar_tickets]
        async with track_async_duration(llm_request_duration_seconds, mode="quick"):
            llm_result = await self._llm.quick_analyze(
                query_ticket_text=text,
                similar_tickets=similar_dicts,
                max_tokens=512,
            )
        llm_tokens_used_total.labels(mode="quick").inc(llm_result.tokens_used)

        response = QuickAnalysisResponse(
            mode="quick",
            jira_id=jira_id,
            fix_summary=llm_result.summary,
            fix_suggestion=llm_result.fix_suggestion,
            similar_tickets=similar_tickets,
            top_similarity_score=round(top_similarity, 4),
            confidence_score=round(confidence.value, 4),
            confidence_label=confidence.label(),
            requires_human_review=bool(review_reasons),
            review_reasons=review_reasons,
            model_version=llm_result.model_version,
            embedding_version=self._embedding.current_version,
            cache_hit=False,
        )

        if review_reasons:
            for reason in review_reasons:
                review_flags_total.labels(reason=reason[:50]).inc()

        # Cache successful response
        await self._cache.set(
            cache_key, response.model_dump(mode="json"), ttl=self._settings.quick_cache_ttl
        )

        return response

    async def _deep_analyze(
        self,
        text: str,
        jira_id: str | None,
        project_key: str | None,
        user_id: str | None,
        ip_address: str | None,
        start_time: float,
    ) -> DeepAnalysisResponse:
        query_vector = await self._embedding.embed_query(text)

        similar_tickets = await self._search.search_similar(
            query_vector,
            top_k=self._settings.deep_analysis_top_k,
            project_key=project_key,
        )

        top_similarity = similar_tickets[0].similarity_score if similar_tickets else 0.0
        top_confidence = similar_tickets[0].confidence_score if similar_tickets else 0.0
        confidence = ConfidenceScore(top_confidence)

        review_reasons = self._check_review_conditions(
            text, confidence.value, similar_tickets
        )

        similar_dicts = [t.model_dump() for t in similar_tickets]
        async with track_async_duration(llm_request_duration_seconds, mode="deep"):
            llm_result = await self._llm.deep_analyze(
                query_ticket_text=text,
                similar_tickets=similar_dicts,
                max_tokens=self._settings.llm_max_tokens,
            )
        llm_tokens_used_total.labels(mode="deep").inc(llm_result.tokens_used)

        related_jira_ids = [t.jira_id for t in similar_tickets[:5]]

        return DeepAnalysisResponse(
            mode="deep",
            jira_id=jira_id,
            root_cause=llm_result.root_cause,
            resolution_reasoning=llm_result.resolution_reasoning,
            risk_notes=llm_result.risk_notes,
            step_by_step_fix=llm_result.step_by_step_fix,
            related_patterns=llm_result.related_patterns,
            related_jira_ids=related_jira_ids,
            similar_tickets=similar_tickets,
            top_similarity_score=round(top_similarity, 4),
            confidence_score=round(confidence.value, 4),
            confidence_label=confidence.label(),
            confidence_explanation=llm_result.confidence_explanation,
            requires_human_review=bool(review_reasons),
            review_reasons=review_reasons,
            model_version=llm_result.model_version,
            embedding_version=self._embedding.current_version,
        )

    def _check_review_conditions(
        self,
        text: str,
        confidence: float,
        similar_tickets: list[SimilarTicketDTO],
    ) -> list[str]:
        reasons: list[str] = []
        threshold = self._settings.confidence_review_threshold

        if confidence < threshold:
            reasons.append(f"low_confidence:{confidence:.2f}")

        if self._search.detect_novel_pattern(similar_tickets):
            reasons.append("novel_pattern")

        text_lower = text.lower()
        for keyword in self._settings.critical_keywords_list:
            if keyword.lower() in text_lower:
                reasons.append(f"critical_keyword:{keyword}")
                break  # One is enough

        return reasons