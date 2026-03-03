"""Shared pytest fixtures."""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Use test environment
os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-min-32-chars-abcdefghij")
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("JIRA_ADAPTER", "mock")
os.environ.setdefault("FAISS_INDEX_PATH", "/tmp/test_faiss")

from app.infrastructure.database.base import Base
import app.models.user  # noqa
import app.models.ticket  # noqa
import app.models.embedding  # noqa
import app.models.feedback  # noqa
import app.models.reranking  # noqa
import app.models.model_registry  # noqa
import app.models.audit_log  # noqa


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.count.return_value = 10
    store.add_vector = AsyncMock(return_value=42)
    store.search = AsyncMock(return_value=[])
    store.persist = AsyncMock()
    store.load = AsyncMock()
    store.rebuild_index = AsyncMock()
    return store


@pytest.fixture
def mock_cache():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    cache.exists = AsyncMock(return_value=False)
    cache.increment = AsyncMock(return_value=1)
    return cache


@pytest.fixture
def sample_vector():
    vec = np.random.randn(384).astype(np.float32)
    return vec / np.linalg.norm(vec)


@pytest.fixture
def sample_ticket_data():
    return {
        "jira_id": "PROJ-1001",
        "project_key": "PROJ",
        "summary": "Database connection pool exhausted under load",
        "description": "Service fails when connection pool is exhausted",
        "status": "Done",
        "resolution": "Increased connection pool size to 50 and added monitoring",
        "priority": "High",
        "labels": ["bug", "database"],
        "components": ["backend"],
        "quality_score": 0.8,
        "is_indexed": False,
    }