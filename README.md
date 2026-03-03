# JIRA Resolution Intelligence Tool

Enterprise-grade AI-powered backend that ingests resolved JIRA tickets, generates semantic embeddings, performs similarity search, and suggests AI-powered resolutions for new issues.

## Architecture

```
app/
├── api/             # FastAPI routes, middleware, dependencies
│   └── v1/
│       └── endpoints/   # auth, analyze, tickets, feedback, admin
├── domain/          # Pure Python — entities, value objects, interfaces, events
│   ├── entities/
│   ├── value_objects/
│   ├── interfaces/  # Ports (abstract adapters)
│   └── exceptions/
├── application/     # Use cases and orchestration services
│   ├── services/    # analysis, ingestion, embedding, search, feedback
│   └── dto/         # Request/response schemas
├── infrastructure/  # Framework implementations
│   ├── database/    # Async SQLAlchemy engine + session
│   ├── cache/       # Redis adapter
│   ├── vector_store/ # FAISS adapter
│   └── scheduler/   # APScheduler background jobs
├── adapters/        # Swappable external system adapters
│   ├── jira/        # MockJiraAdapter + RealJiraAdapter
│   └── llm/         # MockLLMAdapter + OpenAILLMAdapter + AnthropicLLMAdapter
│                    # MockEmbeddingAdapter + OpenAIEmbeddingAdapter + SentenceTransformerAdapter
├── models/          # SQLAlchemy ORM models
├── repositories/    # Async data access layer
├── security/        # JWT, bcrypt, RBAC, rate limiting
├── observability/   # structlog + Prometheus metrics
└── workers/         # Background job handlers
```

### Clean Architecture Layers

```
api → application → domain (no external deps)
api → infrastructure   (implements domain interfaces)
adapters → domain      (implements domain ports)
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- GNU Make

### 1. Start all services

```bash
make up
```

This will:
1. Build the Docker image
2. Start PostgreSQL, Redis, and the backend
3. Run Alembic migrations
4. Seed the database with test data

### 2. Access the API

| Endpoint       | URL                            |
|----------------|--------------------------------|
| API Docs       | http://localhost:8000/docs     |
| Health         | http://localhost:8000/health   |
| Readiness      | http://localhost:8000/ready    |
| Metrics        | http://localhost:8000/metrics  |
| Prometheus     | http://localhost:9090          |

### 3. Authenticate

```bash
# Login as admin
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "AdminPass123!"}'
```

Default users (created by seed script):

| Role     | Email                  | Password          |
|----------|------------------------|-------------------|
| admin    | admin@example.com      | AdminPass123!     |
| reviewer | reviewer@example.com   | ReviewerPass123!  |
| user     | user@example.com       | UserPass123!      |

### 4. Run Quick Analysis

```bash
TOKEN="<your-access-token>"

curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Service is timing out with connection pool exhausted errors under high load. All database queries are failing with timeout exceptions.",
    "mode": "quick"
  }'
```

### 5. Run Deep Analysis (requires reviewer/admin)

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Memory usage growing unbounded in background worker process. OOMKilled every 6-8 hours.",
    "mode": "deep"
  }'
```

### 6. Submit Feedback

```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query_ticket_id": "PROJ-NEW-1",
    "suggested_ticket_id": "<ticket-db-id-from-analysis>",
    "similarity_score": 0.87,
    "confidence_score": 0.79,
    "model_version": "mock-llm-v1.0",
    "embedding_version": "mock-v1-dim384",
    "rating": 5,
    "was_helpful": true,
    "was_correct": true,
    "notes": "Exact same issue, resolution worked perfectly"
  }'
```

## Configuration

All configuration is via environment variables. See `.env.example` for all options.

### Key configuration options

```bash
# Switch to real JIRA (requires API token)
JIRA_ADAPTER=real
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_USERNAME=you@company.com
JIRA_API_TOKEN=your-token
JIRA_PROJECT_KEYS=PROJ,INFRA,PLATFORM

# Switch to OpenAI for embeddings and LLM
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002
EMBEDDING_DIMENSION=1536

LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...

# Or use Anthropic
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-4-6
ANTHROPIC_API_KEY=sk-ant-...

# Or use local SentenceTransformers (no API key needed)
EMBEDDING_PROVIDER=sentence_transformer
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
FAISS_INDEX_DIMENSION=384
```

## API Reference

### Authentication

| Method | Path                    | Description           | Auth  |
|--------|-------------------------|-----------------------|-------|
| POST   | /api/v1/auth/login      | Login, get JWT tokens | No    |
| POST   | /api/v1/auth/refresh    | Refresh access token  | No    |
| GET    | /api/v1/auth/me         | Get current user      | Yes   |
| POST   | /api/v1/auth/register   | Create user (admin)   | Admin |

### Analysis

| Method | Path           | Description           | Auth     |
|--------|----------------|-----------------------|----------|
| POST   | /api/v1/analyze | Analyze ticket       | User+    |

**Quick mode** target: < 1.5s | **Deep mode** target: < 5s

### Tickets

| Method | Path                        | Description           | Auth  |
|--------|-----------------------------|-----------------------|-------|
| GET    | /api/v1/tickets             | List tickets          | User  |
| GET    | /api/v1/tickets/{id}        | Get ticket by ID      | User  |
| POST   | /api/v1/tickets/sync        | Trigger JIRA sync     | Admin |
| POST   | /api/v1/tickets/sync/{jira_id} | Sync single ticket | Admin |
| GET    | /api/v1/tickets/stats/by-project | Stats by project | User  |

### Feedback

| Method | Path                     | Description              | Auth     |
|--------|--------------------------|--------------------------|----------|
| POST   | /api/v1/feedback         | Submit feedback          | User+    |
| GET    | /api/v1/feedback/stats   | Feedback statistics      | Reviewer |
| GET    | /api/v1/feedback/weights | Reranking weights        | Admin    |
| POST   | /api/v1/feedback/aggregate | Trigger aggregation    | Admin    |

### Admin

| Method | Path                         | Description           | Auth  |
|--------|------------------------------|-----------------------|-------|
| POST   | /api/v1/admin/reindex        | Rebuild FAISS index   | Admin |
| GET    | /api/v1/admin/embedding-health | Embedding health    | Admin |
| GET    | /api/v1/admin/audit-logs     | Audit log viewer      | Admin |
| GET    | /api/v1/admin/system-status  | Full system status    | Admin |

### Health

| Method | Path      | Description            | Auth |
|--------|-----------|------------------------|------|
| GET    | /health   | Liveness check         | No   |
| GET    | /ready    | Readiness check        | No   |
| GET    | /metrics  | Prometheus metrics     | No   |

## RBAC Roles

| Permission      | User | Reviewer | Admin |
|-----------------|------|----------|-------|
| analyze:quick   | ✓    | ✓        | ✓     |
| analyze:deep    |      | ✓        | ✓     |
| tickets:read    | ✓    | ✓        | ✓     |
| tickets:sync    |      |          | ✓     |
| feedback:write  | ✓    | ✓        | ✓     |
| feedback:read   |      | ✓        | ✓     |
| admin:reindex   |      |          | ✓     |
| admin:users     |      |          | ✓     |

## Feedback Loop & Safe Learning

The feedback loop is designed to be **safe** — it never auto-fine-tunes models or blindly applies feedback. Instead:

1. Users submit feedback (rating 1-5, was_helpful, was_correct)
2. Feedback is aggregated nightly with **exponential decay** (old feedback weighted less)
3. Reranking weights are updated **only when `FEEDBACK_MIN_SAMPLES` threshold is met**
4. Weights affect the reranking score for future searches (not the embedding model itself)
5. Confidence calibration adjusts based on historical signal

### Human Review Flags

Analysis results are flagged for manual review when:
- Confidence score < `CONFIDENCE_REVIEW_THRESHOLD` (default: 0.60)
- No similar tickets found (novel pattern)
- Query text contains critical keywords (production, outage, data-loss, security, breach)

## Background Jobs

| Job                    | Schedule    | Description                        |
|------------------------|-------------|------------------------------------|
| JIRA Incremental Sync  | */30 * * * * | Fetch new resolved tickets        |
| Feedback Aggregation   | 0 2 * * *   | Update reranking weights           |
| Embedding Health Check | 0 * * * *   | Index unindexed tickets            |

## Development Commands

```bash
make up              # Start everything
make down            # Stop everything
make logs            # Tail backend logs
make shell           # Open bash in container
make migrate         # Run migrations
make seed            # Seed test data
make test            # Run test suite
make test-unit       # Unit tests only
make lint            # Run ruff linter
make fmt             # Format code
make clean           # Remove build artifacts
make clean-data      # Remove all volumes (destructive!)
```

## Prometheus Metrics

Key metrics exposed at `/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `jira_intel_http_request_duration_seconds` | Histogram | API latency p50/p95/p99 |
| `jira_intel_embedding_generation_seconds` | Histogram | Embedding time |
| `jira_intel_vector_search_seconds` | Histogram | FAISS search time |
| `jira_intel_llm_request_seconds{mode}` | Histogram | LLM analysis time |
| `jira_intel_cache_hits_total` | Counter | Cache hit count |
| `jira_intel_feedback_submitted_total` | Counter | Feedback submissions |
| `jira_intel_feedback_acceptance_rate` | Gauge | was_helpful rate |
| `jira_intel_confidence_scores{mode}` | Histogram | Confidence distribution |
| `jira_intel_review_flags_total{reason}` | Counter | Human review flags |
| `jira_intel_indexed_tickets_total` | Gauge | FAISS index size |
| `jira_intel_tickets_ingested_total` | Counter | Ingested tickets |