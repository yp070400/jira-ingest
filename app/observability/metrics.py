"""Prometheus metrics registry."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ── Request Metrics ────────────────────────────────────────────────────────
http_requests_total = Counter(
    "jira_intel_http_requests_total",
    "Total HTTP requests by method, endpoint, and status code",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "jira_intel_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.5, 5.0, 10.0],
)

# ── Embedding Metrics ──────────────────────────────────────────────────────
embedding_generation_duration_seconds = Histogram(
    "jira_intel_embedding_generation_seconds",
    "Time to generate a single embedding",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)

embedding_batch_size = Histogram(
    "jira_intel_embedding_batch_size",
    "Batch size for embedding generation",
    buckets=[1, 5, 10, 20, 50, 100],
)

total_indexed_tickets = Gauge(
    "jira_intel_indexed_tickets_total",
    "Total number of tickets indexed in FAISS",
)

# ── Vector Search Metrics ──────────────────────────────────────────────────
vector_search_duration_seconds = Histogram(
    "jira_intel_vector_search_seconds",
    "Time to perform FAISS vector search",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

vector_search_results_count = Histogram(
    "jira_intel_vector_search_results",
    "Number of results returned by vector search",
    buckets=[0, 1, 2, 3, 5, 10],
)

# ── LLM Metrics ───────────────────────────────────────────────────────────
llm_request_duration_seconds = Histogram(
    "jira_intel_llm_request_seconds",
    "Time for LLM to generate analysis",
    ["mode"],  # quick | deep
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0],
)

llm_tokens_used_total = Counter(
    "jira_intel_llm_tokens_total",
    "Total LLM tokens consumed",
    ["mode"],
)

# ── Cache Metrics ──────────────────────────────────────────────────────────
cache_hits_total = Counter(
    "jira_intel_cache_hits_total",
    "Total cache hits",
    ["cache_type"],
)

cache_misses_total = Counter(
    "jira_intel_cache_misses_total",
    "Total cache misses",
    ["cache_type"],
)

# ── Ingestion Metrics ──────────────────────────────────────────────────────
tickets_ingested_total = Counter(
    "jira_intel_tickets_ingested_total",
    "Total JIRA tickets ingested",
    ["project_key", "is_new"],
)

ingestion_errors_total = Counter(
    "jira_intel_ingestion_errors_total",
    "Total ingestion errors",
    ["error_type"],
)

# ── Feedback Metrics ───────────────────────────────────────────────────────
feedback_submitted_total = Counter(
    "jira_intel_feedback_submitted_total",
    "Total feedback submissions",
    ["rating_bucket"],  # positive (4-5), neutral (3), negative (1-2)
)

feedback_acceptance_rate = Gauge(
    "jira_intel_feedback_acceptance_rate",
    "Rolling acceptance rate of AI suggestions (was_helpful ratio)",
)

# ── Confidence & Review Metrics ────────────────────────────────────────────
confidence_score_histogram = Histogram(
    "jira_intel_confidence_scores",
    "Distribution of confidence scores",
    ["mode"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

review_flags_total = Counter(
    "jira_intel_review_flags_total",
    "Total human review flags raised",
    ["reason"],
)

# ── Analysis Metrics ───────────────────────────────────────────────────────
analysis_requests_total = Counter(
    "jira_intel_analysis_requests_total",
    "Total analysis requests",
    ["mode"],
)

analysis_cache_hits_total = Counter(
    "jira_intel_analysis_cache_hits_total",
    "Analysis requests served from cache",
    ["mode"],
)

# ── System Metrics ─────────────────────────────────────────────────────────
active_users_gauge = Gauge(
    "jira_intel_active_users",
    "Number of active users in the system",
)

scheduler_job_runs_total = Counter(
    "jira_intel_scheduler_job_runs_total",
    "Total background scheduler job executions",
    ["job_name", "status"],
)

# ── Helpers ───────────────────────────────────────────────────────────────

@contextmanager
def track_duration(histogram: Histogram, **labels) -> Generator:
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        if labels:
            histogram.labels(**labels).observe(duration)
        else:
            histogram.observe(duration)


@asynccontextmanager
async def track_async_duration(histogram: Histogram, **labels) -> AsyncGenerator:
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        if labels:
            histogram.labels(**labels).observe(duration)
        else:
            histogram.observe(duration)


def get_metrics_response() -> tuple[bytes, str]:
    """Return Prometheus metrics as bytes and content type."""
    return generate_latest(), CONTENT_TYPE_LATEST


def rating_to_bucket(rating: int) -> str:
    if rating >= 4:
        return "positive"
    elif rating == 3:
        return "neutral"
    return "negative"