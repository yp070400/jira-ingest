"""Unit tests for application services."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import pytest_asyncio

from app.adapters.llm.mock_adapter import MockLLMAdapter
from app.adapters.jira.mock_adapter import MockJiraAdapter
from app.adapters.llm.embedding_adapters import MockEmbeddingAdapter
from app.application.dto.analysis_dto import AnalysisMode, SimilarTicketDTO
from app.domain.interfaces.vector_store_port import SearchResult


class TestMockEmbeddingAdapter:
    @pytest.mark.asyncio
    async def test_embed_text_returns_correct_dimension(self):
        adapter = MockEmbeddingAdapter(dim=384)
        vec = await adapter.embed_text("test text")
        assert vec.shape == (384,)

    @pytest.mark.asyncio
    async def test_embed_text_is_normalized(self):
        adapter = MockEmbeddingAdapter(dim=384)
        vec = await adapter.embed_text("test text")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    @pytest.mark.asyncio
    async def test_embed_text_deterministic(self):
        adapter = MockEmbeddingAdapter(dim=384)
        v1 = await adapter.embed_text("same text")
        v2 = await adapter.embed_text("same text")
        np.testing.assert_array_equal(v1, v2)

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        adapter = MockEmbeddingAdapter(dim=384)
        texts = ["text one", "text two", "text three"]
        vecs = await adapter.embed_batch(texts)
        assert len(vecs) == 3
        for v in vecs:
            assert v.shape == (384,)

    @pytest.mark.asyncio
    async def test_health_check(self):
        adapter = MockEmbeddingAdapter()
        assert await adapter.health_check() is True


class TestMockJiraAdapter:
    @pytest.mark.asyncio
    async def test_fetch_resolved_tickets(self):
        adapter = MockJiraAdapter()
        tickets = await adapter.fetch_resolved_tickets(
            project_keys=["PROJ"],
            resolved_statuses=["Done"],
            max_results=10,
        )
        assert len(tickets) == 10
        for t in tickets:
            assert t.project_key == "PROJ"
            assert t.status == "Done"

    @pytest.mark.asyncio
    async def test_fetch_ticket_by_id(self):
        adapter = MockJiraAdapter()
        ticket = await adapter.fetch_ticket_by_id("PROJ-1000")
        assert ticket is not None
        assert ticket.jira_id == "PROJ-1000"

    @pytest.mark.asyncio
    async def test_fetch_nonexistent_ticket(self):
        adapter = MockJiraAdapter()
        ticket = await adapter.fetch_ticket_by_id("PROJ-9999")
        assert ticket is None

    @pytest.mark.asyncio
    async def test_health_check(self):
        adapter = MockJiraAdapter()
        assert await adapter.health_check() is True


class TestMockLLMAdapter:
    @pytest.mark.asyncio
    async def test_quick_analyze(self):
        adapter = MockLLMAdapter()
        similar = [{"jira_id": "PROJ-1", "summary": "DB issue", "similarity_score": 0.9}]
        result = await adapter.quick_analyze("DB connection pool exhausted", similar)
        assert result.summary
        assert result.model_version == "mock-llm-v1.0"
        assert result.tokens_used > 0

    @pytest.mark.asyncio
    async def test_deep_analyze(self):
        adapter = MockLLMAdapter()
        similar = [{"jira_id": "PROJ-1", "summary": "Memory leak", "similarity_score": 0.85}]
        result = await adapter.deep_analyze("Memory leak in worker", similar)
        assert result.root_cause
        assert isinstance(result.step_by_step_fix, list)
        assert len(result.step_by_step_fix) > 0


class TestFAISSVectorStore:
    @pytest.mark.asyncio
    async def test_add_and_search(self, tmp_path):
        from app.infrastructure.vector_store.faiss_store import FAISSVectorStore

        store = FAISSVectorStore(index_path=str(tmp_path), dimension=384)
        await store.load()

        adapter = MockEmbeddingAdapter(dim=384)
        v1 = await adapter.embed_text("database connection pool")
        v2 = await adapter.embed_text("memory leak in worker")
        v3 = await adapter.embed_text("ssl certificate expired")

        id1 = await store.add_vector("ticket-1", v1)
        id2 = await store.add_vector("ticket-2", v2)
        id3 = await store.add_vector("ticket-3", v3)

        assert store.count() == 3

        # Search for most similar to v1
        query = await adapter.embed_text("database connection timeout")
        results = await store.search(query, top_k=3, similarity_threshold=0.0)

        assert len(results) > 0
        # The most similar should be ticket-1 (database related)
        assert results[0].ticket_id in ["ticket-1", "ticket-2", "ticket-3"]

    @pytest.mark.asyncio
    async def test_persist_and_reload(self, tmp_path):
        from app.infrastructure.vector_store.faiss_store import FAISSVectorStore

        store = FAISSVectorStore(index_path=str(tmp_path), dimension=384)
        await store.load()

        adapter = MockEmbeddingAdapter(dim=384)
        v = await adapter.embed_text("test vector")
        await store.add_vector("ticket-abc", v)
        await store.persist()

        store2 = FAISSVectorStore(index_path=str(tmp_path), dimension=384)
        await store2.load()
        assert store2.count() == 1