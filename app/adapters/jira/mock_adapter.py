"""Mock JIRA adapter for local development and testing."""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.domain.entities.ticket import TicketEntity, TicketPriority, TicketStatus
from app.domain.interfaces.jira_port import JiraPort

_MOCK_SUMMARIES = [
    "Service unavailable after deployment — connection pool exhausted",
    "Memory leak in worker process causing OOM kills",
    "API gateway returns 502 intermittently under high load",
    "Database deadlock on concurrent write operations",
    "Redis cache invalidation not propagating to all nodes",
    "Authentication service latency spike during peak hours",
    "File upload fails silently for files over 100MB",
    "CRON job duplicate execution in multi-pod environment",
    "SSL certificate renewal not reflecting in load balancer",
    "Kafka consumer group rebalancing causing message loss",
    "Search index out of sync after bulk data migration",
    "User session not expiring after password change",
    "Email notification queue backlog under high user activity",
    "Health check endpoint timing out when DB is slow",
    "Rate limiter not respecting per-user quotas correctly",
    "GraphQL N+1 query performance regression",
    "Docker container restart loop due to missing env var",
    "CDN cache not purging on content update",
    "Webhook delivery retry storm after target outage",
    "Configuration hot-reload fails on Kubernetes rolling update",
    "CI/CD pipeline fails intermittently on test flakiness",
    "Terraform state lock not released after interrupted apply",
    "Log aggregation dropping events at high throughput",
    "Distributed trace correlation IDs not propagating through async tasks",
    "Feature flag evaluation throwing NPE for new users",
]

_MOCK_RESOLUTIONS = [
    "Increased connection pool size from 10 to 50 and added pool monitoring alerts.",
    "Identified memory leak in event listener registration — added cleanup in component unmount.",
    "Added circuit breaker pattern with 5-second timeout and configured upstream health checks.",
    "Resolved by adding SELECT FOR UPDATE SKIP LOCKED to prevent concurrent write contention.",
    "Updated Redis pub/sub channel to broadcast invalidation events to all replicas.",
    "Implemented request coalescing in auth service and added connection pooling to LDAP.",
    "Added streaming upload support with chunked transfer encoding; 100MB limit raised to 5GB.",
    "Added distributed lock using Redis SETNX with TTL before CRON execution.",
    "Updated Nginx upstream block to use shared SSL session cache; re-provisioned ACM cert.",
    "Tuned consumer group session.timeout.ms and max.poll.interval.ms to match processing SLA.",
    "Implemented async re-indexing pipeline with change-data-capture on PostgreSQL WAL.",
    "Added session invalidation hook on password change event in authentication service.",
    "Scaled email worker replicas from 2 to 8; added DLQ for failed deliveries.",
    "Added health check isolation from main DB pool; uses dedicated read replica.",
    "Fixed rate limiter sliding window algorithm — was using fixed window causing burst over-limit.",
    "Added DataLoader pattern to batch-resolve related entities in single SQL query.",
    "Added required ENV_VAR to deployment manifest and updated Helm chart defaults.",
    "Implemented cache-busting query param versioning and added purge webhook on publish.",
    "Added exponential backoff with jitter (max 5 retries) and circuit breaker for webhook delivery.",
    "Fixed ConfigMap hot-reload by using inotify watcher instead of polling interval.",
    "Isolated flaky tests to separate suite with retry logic; root cause was port collision.",
    "Added Terraform state lock timeout handler and cleanup script in pipeline.",
    "Upgraded Filebeat to 8.x; fixed pipeline filter dropping events on parse error.",
    "Updated async task headers to propagate traceparent/tracestate via OpenTelemetry baggage.",
    "Fixed null check for new user cohort in feature flag evaluation service.",
]

_MOCK_COMPONENTS = [
    ["backend", "api-gateway"],
    ["backend", "database"],
    ["infrastructure", "kubernetes"],
    ["backend", "auth-service"],
    ["backend", "cache"],
    ["frontend", "api-client"],
    ["infrastructure", "ci-cd"],
    ["backend", "workers"],
    ["infrastructure", "networking"],
    ["backend", "search"],
]

_MOCK_LABELS = [
    ["bug", "production", "p1"],
    ["performance", "memory"],
    ["infrastructure", "k8s"],
    ["security", "auth"],
    ["reliability", "database"],
    ["bug", "upload"],
    ["infrastructure", "ci"],
    ["performance", "cache"],
    ["reliability", "webhook"],
    ["observability", "logging"],
]


def _make_ticket(idx: int, project_key: str) -> TicketEntity:
    rng = random.Random(idx)
    summary = rng.choice(_MOCK_SUMMARIES)
    resolution = rng.choice(_MOCK_RESOLUTIONS)
    priority = rng.choice([p.value for p in TicketPriority])
    labels = rng.choice(_MOCK_LABELS)
    components = rng.choice(_MOCK_COMPONENTS)
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=rng.randint(30, 365))
    resolved = created + timedelta(days=rng.randint(1, 14))

    ticket = TicketEntity(
        jira_id=f"{project_key}-{1000 + idx}",
        project_key=project_key,
        summary=summary,
        description=(
            f"This issue was reported by the on-call team. "
            f"Symptoms: {summary.lower()}. "
            f"Observed in production environment. "
            f"Impact: partial service degradation. "
            f"Reproduces consistently under load."
        ),
        status=TicketStatus.DONE.value,
        resolution=resolution,
        priority=priority,
        reporter=f"user{rng.randint(1, 20)}@example.com",
        assignee=f"engineer{rng.randint(1, 10)}@example.com",
        labels=labels,
        components=components,
        fix_versions=[f"v{rng.randint(1, 5)}.{rng.randint(0, 12)}.{rng.randint(0, 9)}"],
        created_at=created,
        resolved_at=resolved,
        raw_data={"comments": [{"body": f"Comment {i}"} for i in range(rng.randint(0, 5))]},
    )
    ticket.compute_quality_score()
    return ticket


class MockJiraAdapter(JiraPort):
    """
    Deterministic mock JIRA adapter.
    Generates realistic synthetic tickets for local development.
    """

    _TOTAL_PER_PROJECT = 50

    async def fetch_resolved_tickets(
        self,
        project_keys: list[str],
        resolved_statuses: list[str],
        since: datetime | None = None,
        max_results: int = 100,
    ) -> list[TicketEntity]:
        await asyncio.sleep(0.05)  # Simulate network latency
        tickets: list[TicketEntity] = []
        for project_key in project_keys:
            for idx in range(self._TOTAL_PER_PROJECT):
                ticket = _make_ticket(idx, project_key)
                if since is not None and ticket.resolved_at and ticket.resolved_at < since:
                    continue
                tickets.append(ticket)
                if len(tickets) >= max_results:
                    return tickets
        return tickets

    async def fetch_ticket_by_id(self, jira_id: str) -> TicketEntity | None:
        await asyncio.sleep(0.02)
        parts = jira_id.split("-")
        if len(parts) != 2:
            return None
        project_key, num_str = parts
        try:
            idx = int(num_str) - 1000
        except ValueError:
            return None
        if not 0 <= idx < self._TOTAL_PER_PROJECT:
            return None
        return _make_ticket(idx, project_key)

    async def health_check(self) -> bool:
        await asyncio.sleep(0.01)
        return True

    async def get_total_count(
        self,
        project_keys: list[str],
        resolved_statuses: list[str],
        since: datetime | None = None,
    ) -> int:
        return len(project_keys) * self._TOTAL_PER_PROJECT