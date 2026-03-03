"""Embedding adapter implementations: Mock, OpenAI, SentenceTransformer."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import TYPE_CHECKING

import numpy as np

from app.config import get_settings
from app.domain.exceptions.domain_exceptions import EmbeddingGenerationError
from app.domain.interfaces.embedding_port import EmbeddingPort

logger = logging.getLogger(__name__)


# ── Mock Adapter ─────────────────────────────────────────────────────────────

class MockEmbeddingAdapter(EmbeddingPort):
    """Deterministic mock embeddings using text hash. Zero API cost."""

    def __init__(self, dim: int | None = None) -> None:
        settings = get_settings()
        self._dim = dim or settings.embedding_dimension
        self._model = "mock-embedding-v1"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def version(self) -> str:
        return f"mock-v1-dim{self._dim}"

    def _text_to_vector(self, text: str) -> np.ndarray:
        """Hash text into a deterministic pseudo-random unit vector."""
        digest = hashlib.sha256(text.encode()).digest()
        seed = int.from_bytes(digest[:4], "big")
        rng = np.random.RandomState(seed)
        vec = rng.randn(self._dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-10 else vec

    async def embed_text(self, text: str) -> np.ndarray:
        return self._text_to_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        return [self._text_to_vector(t) for t in texts]

    async def health_check(self) -> bool:
        return True


# ── OpenAI Adapter ────────────────────────────────────────────────────────────

class OpenAIEmbeddingAdapter(EmbeddingPort):
    """OpenAI text-embedding-ada-002 / text-embedding-3-* adapter."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.embedding_model
        self._dim = settings.embedding_dimension

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def version(self) -> str:
        return f"openai-{self._model}"

    async def embed_text(self, text: str) -> np.ndarray:
        try:
            response = await self._client.embeddings.create(
                input=[text[:8191]],
                model=self._model,
            )
            vec = np.array(response.data[0].embedding, dtype=np.float32)
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 1e-10 else vec
        except Exception as e:
            raise EmbeddingGenerationError(str(e)) from e

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        try:
            truncated = [t[:8191] for t in texts]
            response = await self._client.embeddings.create(
                input=truncated,
                model=self._model,
            )
            results = []
            for item in response.data:
                vec = np.array(item.embedding, dtype=np.float32)
                norm = np.linalg.norm(vec)
                results.append(vec / norm if norm > 1e-10 else vec)
            return results
        except Exception as e:
            raise EmbeddingGenerationError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            await self.embed_text("health check ping")
            return True
        except Exception:
            return False


# ── SentenceTransformer Adapter ───────────────────────────────────────────────

class SentenceTransformerEmbeddingAdapter(EmbeddingPort):
    """Local HuggingFace SentenceTransformer — no API key needed."""

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.embedding_model or "all-MiniLM-L6-v2"
        self._model = None  # Lazy load

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading SentenceTransformer model: %s", self._model_name)
                self._model = SentenceTransformer(self._model_name)
                logger.info(
                    "SentenceTransformer loaded, dim=%d", self._model.get_sentence_embedding_dimension()
                )
            except ImportError as e:
                raise EmbeddingGenerationError(
                    "sentence-transformers not installed. Run: pip install sentence-transformers"
                ) from e
        return self._model

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._get_model().get_sentence_embedding_dimension()

    @property
    def version(self) -> str:
        return f"st-{self._model_name.replace('/', '-')}"

    async def embed_text(self, text: str) -> np.ndarray:
        import asyncio

        model = self._get_model()
        loop = asyncio.get_event_loop()
        vec = await loop.run_in_executor(
            None, lambda: model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        )
        return vec.astype(np.float32)

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        import asyncio

        model = self._get_model()
        loop = asyncio.get_event_loop()
        vecs = await loop.run_in_executor(
            None,
            lambda: model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32),
        )
        return [v.astype(np.float32) for v in vecs]

    async def health_check(self) -> bool:
        try:
            self._get_model()
            return True
        except Exception:
            return False


# ── Factory ───────────────────────────────────────────────────────────────────

def get_embedding_adapter() -> EmbeddingPort:
    settings = get_settings()
    provider = settings.embedding_provider
    if provider == "openai":
        return OpenAIEmbeddingAdapter()
    elif provider == "sentence_transformer":
        return SentenceTransformerEmbeddingAdapter()
    else:
        return MockEmbeddingAdapter()


def get_llm_adapter():
    """Factory for LLM adapters."""
    from app.adapters.llm.mock_adapter import MockLLMAdapter
    from app.adapters.llm.openai_adapter import OpenAILLMAdapter
    from app.adapters.llm.anthropic_adapter import AnthropicLLMAdapter

    settings = get_settings()
    provider = settings.llm_provider
    if provider == "openai":
        return OpenAILLMAdapter()
    elif provider == "anthropic":
        return AnthropicLLMAdapter()
    else:
        return MockLLMAdapter()


def get_jira_adapter():
    """Factory for JIRA adapters."""
    from app.adapters.jira.mock_adapter import MockJiraAdapter
    from app.adapters.jira.real_adapter import RealJiraAdapter

    settings = get_settings()
    if settings.jira_adapter == "real":
        return RealJiraAdapter()
    return MockJiraAdapter()