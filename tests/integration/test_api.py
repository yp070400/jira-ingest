"""Integration tests for the FastAPI endpoints."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("JIRA_ADAPTER", "mock")
os.environ.setdefault("SECRET_KEY", "test-secret-key-min-32-chars-abcdefghij")


@pytest.fixture(autouse=True)
def mock_infrastructure(mock_vector_store, mock_cache):
    """Mock heavy infrastructure for all integration tests."""
    with patch("app.api.dependencies.get_vector_store", return_value=mock_vector_store), \
         patch("app.api.dependencies.get_cache", return_value=mock_cache):
        yield


@pytest.fixture
def admin_token():
    from app.security.jwt_handler import create_access_token
    return create_access_token("admin-user-id", "admin", extra_claims={"email": "admin@test.com"})


@pytest.fixture
def user_token():
    from app.security.jwt_handler import create_access_token
    return create_access_token("user-id", "user", extra_claims={"email": "user@test.com"})


@pytest.fixture
def reviewer_token():
    from app.security.jwt_handler import create_access_token
    return create_access_token("reviewer-id", "reviewer", extra_claims={"email": "reviewer@test.com"})


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_login_with_invalid_credentials_returns_401(self, db_session):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "notexist@example.com", "password": "WrongPass123!"},
            )
        assert response.status_code == 401


class TestAnalyzeEndpoints:
    @pytest.mark.asyncio
    async def test_analyze_requires_auth(self):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze",
                json={"text": "Service is down", "mode": "quick"},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_quick_analyze_with_valid_token(
        self, mock_vector_store, mock_cache, user_token
    ):
        from app.main import app
        from app.application.dto.analysis_dto import SimilarTicketDTO
        from datetime import datetime, timezone

        mock_vector_store.search = AsyncMock(return_value=[])
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        headers = {"Authorization": f"Bearer {user_token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("app.application.services.analysis_service.AnalysisService.analyze") as mock_analyze:
                from app.application.dto.analysis_dto import QuickAnalysisResponse
                mock_analyze.return_value = QuickAnalysisResponse(
                    fix_summary="Increase connection pool size",
                    fix_suggestion="Based on PROJ-1001",
                    similar_tickets=[],
                    top_similarity_score=0.85,
                    confidence_score=0.78,
                    confidence_label="MEDIUM",
                    requires_human_review=False,
                    model_version="mock-v1",
                    embedding_version="mock-embed-v1",
                )
                response = await client.post(
                    "/api/v1/analyze",
                    json={"text": "Database connection pool is exhausted under high load", "mode": "quick"},
                    headers=headers,
                )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_deep_analyze_requires_reviewer_role(self, user_token):
        from app.main import app
        headers = {"Authorization": f"Bearer {user_token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze",
                json={"text": "Database connection pool exhausted", "mode": "deep"},
                headers=headers,
            )
        assert response.status_code == 403


class TestFeedbackEndpoints:
    @pytest.mark.asyncio
    async def test_submit_feedback_requires_auth(self):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/feedback",
                json={
                    "query_ticket_id": "PROJ-100",
                    "suggested_ticket_id": "uuid-123",
                    "similarity_score": 0.85,
                    "confidence_score": 0.75,
                    "model_version": "mock-v1",
                    "embedding_version": "mock-v1",
                    "rating": 4,
                    "was_helpful": True,
                    "was_correct": True,
                },
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_feedback_validation_rejects_invalid_rating(self, user_token):
        from app.main import app
        headers = {"Authorization": f"Bearer {user_token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/feedback",
                json={
                    "query_ticket_id": "PROJ-100",
                    "suggested_ticket_id": "uuid-123",
                    "similarity_score": 0.85,
                    "confidence_score": 0.75,
                    "model_version": "mock-v1",
                    "embedding_version": "mock-v1",
                    "rating": 10,  # invalid
                    "was_helpful": True,
                    "was_correct": True,
                },
                headers=headers,
            )
        assert response.status_code == 422


class TestAdminEndpoints:
    @pytest.mark.asyncio
    async def test_admin_endpoints_require_admin_role(self, user_token):
        from app.main import app
        headers = {"Authorization": f"Bearer {user_token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/admin/reindex", headers=headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reviewer_cannot_access_admin(self, reviewer_token):
        from app.main import app
        headers = {"Authorization": f"Bearer {reviewer_token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/admin/audit-logs", headers=headers)
        assert response.status_code == 403