from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env.dev"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "JIRA Resolution Intelligence"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── Server ───────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    # ── Security ─────────────────────────────────────────────────────────────
    secret_key: str = Field(..., min_length=32)
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://jira_user:jira_pass@localhost:5432/jira_intel"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600
    redis_max_connections: int = 20

    # ── FAISS Vector Store ────────────────────────────────────────────────────
    faiss_index_path: str = "/app/data/faiss"
    faiss_index_dimension: int = 1536
    faiss_similarity_threshold: float = 0.70
    novelty_threshold: float = 0.40

    # ── Embedding ─────────────────────────────────────────────────────────────
    embedding_provider: Literal["mock", "openai", "sentence_transformer"] = "mock"
    embedding_model: str = "text-embedding-ada-002"
    embedding_dimension: int = 1536
    embedding_batch_size: int = 32

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider: Literal["mock", "openai", "anthropic"] = "mock"
    llm_model: str = "gpt-4o"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.2

    # ── API Keys ──────────────────────────────────────────────────────────────
    openai_api_key: str = "sk-placeholder"
    anthropic_api_key: str = "sk-ant-placeholder"

    # ── JIRA ──────────────────────────────────────────────────────────────────
    jira_adapter: Literal["mock", "real"] = "mock"
    jira_base_url: str = "https://mock.atlassian.net"
    jira_username: str = "dev@example.com"
    jira_api_token: str = "mock-token"
    # 3 = Atlassian Cloud  |  2 = self-hosted Server / Data Center
    jira_api_version: int = 3
    jira_project_keys: str = "PROJ,INFRA"
    jira_sync_interval_minutes: int = 30
    jira_max_results_per_page: int = 100
    jira_resolved_statuses: str = "Done,Resolved,Closed"

    # ── Analysis ─────────────────────────────────────────────────────────────
    quick_analysis_top_k: int = 5
    deep_analysis_top_k: int = 10
    quick_cache_ttl: int = 1800
    confidence_review_threshold: float = 0.60
    critical_keywords: str = "production,outage,data-loss,security,breach,critical"

    # ── Feedback & Reranking ──────────────────────────────────────────────────
    feedback_min_samples: int = 10
    feedback_decay_lambda: float = 0.1
    reranking_similarity_weight: float = 1.0
    reranking_recency_weight: float = 0.2
    reranking_feedback_weight: float = 0.3
    reranking_quality_weight: float = 0.2

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    rate_limit_deep_requests: int = 10
    rate_limit_deep_window_seconds: int = 60

    # ── Background Jobs ───────────────────────────────────────────────────────
    ingestion_cron: str = "*/30 * * * *"
    feedback_aggregation_cron: str = "0 2 * * *"
    embedding_health_cron: str = "0 * * * *"

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    cors_allow_credentials: bool = True

    # ── Computed Properties ───────────────────────────────────────────────────
    @property
    def jira_project_keys_list(self) -> list[str]:
        return [k.strip() for k in self.jira_project_keys.split(",") if k.strip()]

    @property
    def jira_resolved_statuses_list(self) -> list[str]:
        return [s.strip() for s in self.jira_resolved_statuses.split(",") if s.strip()]

    @property
    def critical_keywords_list(self) -> list[str]:
        return [k.strip() for k in self.critical_keywords.split(",") if k.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("faiss_similarity_threshold", "novelty_threshold", "confidence_review_threshold")
    @classmethod
    def validate_probability(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Must be between 0.0 and 1.0")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()