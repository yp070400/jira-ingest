"""Mock LLM adapter for local development — no API keys required."""
from __future__ import annotations

import asyncio
import random
from typing import Any

from app.domain.interfaces.llm_port import DeepAnalysisResult, LLMPort, QuickAnalysisResult


class MockLLMAdapter(LLMPort):
    """Returns realistic-looking deterministic mock responses."""

    _QUICK_SUMMARIES = [
        (
            "Root cause identified as exhausted database connection pool under burst traffic. "
            "Apply fix by increasing pool_size to 50 and adding connection timeout handling. "
            "Monitor pg_stat_activity to confirm resolution. "
            "Deploy during low-traffic window and verify with load test."
        ),
        (
            "Service timeout caused by synchronous blocking call in async request handler. "
            "Refactor to use asyncio.create_task and add circuit breaker pattern. "
            "Increase upstream timeout from 5s to 15s as temporary mitigation. "
            "Long-term: migrate to event-driven architecture for this subsystem."
        ),
        (
            "Memory leak traced to unclosed file handles in background worker process. "
            "Fix by adding explicit close() calls in finally blocks and using context managers. "
            "Restart workers nightly as interim workaround. "
            "Add heap profiling to CI pipeline to catch future regressions."
        ),
        (
            "Cache invalidation race condition between write and read replicas. "
            "Implement write-through cache with 100ms propagation delay. "
            "Add cache version header to detect stale responses. "
            "Consider switching to read-your-writes consistency model."
        ),
        (
            "Authentication failure caused by clock skew between service pods. "
            "Ensure NTP sync is configured across all nodes. "
            "Increase JWT clock skew tolerance from 0s to 30s. "
            "Add monitoring alert for clock drift > 10 seconds."
        ),
    ]

    _ROOT_CAUSES = [
        "Thread contention in shared connection pool causing request queuing and cascading timeouts.",
        "Memory not released after event listener deregistration — long-running process accumulates over hours.",
        "Misconfigured retry policy causing exponential traffic amplification to downstream service.",
        "Lack of idempotency key in distributed write path leading to duplicate processing.",
        "Certificate pinning bypass due to expired intermediate CA not refreshed in trust store.",
    ]

    _RISK_NOTES = [
        "Changing pool configuration requires service restart — coordinate with on-call team.",
        "Memory fix requires careful testing under sustained load — regression risk is moderate.",
        "Circuit breaker threshold tuning may increase error rate briefly during calibration.",
        "Distributed lock implementation must handle Redis failover — test with chaos engineering.",
        "SSL certificate rotation has hard deadline — escalate if delayed.",
    ]

    @property
    def model_version(self) -> str:
        return "mock-llm-v1.0"

    async def quick_analyze(
        self,
        query_ticket_text: str,
        similar_tickets: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> QuickAnalysisResult:
        await asyncio.sleep(0.1)  # Simulate LLM latency
        rng = random.Random(hash(query_ticket_text[:50]))
        summary = rng.choice(self._QUICK_SUMMARIES)
        best_match = similar_tickets[0] if similar_tickets else {}

        return QuickAnalysisResult(
            summary=summary,
            fix_suggestion=(
                f"Based on similar issue {best_match.get('jira_id', 'N/A')} "
                f"(similarity: {best_match.get('similarity_score', 0):.2f}): "
                f"{summary.split('.')[0]}."
            ),
            model_version=self.model_version,
            tokens_used=rng.randint(200, 400),
            raw_response={"mock": True, "model": self.model_version},
        )

    async def deep_analyze(
        self,
        query_ticket_text: str,
        similar_tickets: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> DeepAnalysisResult:
        await asyncio.sleep(0.3)
        rng = random.Random(hash(query_ticket_text[:80]))
        related_ids = [t.get("jira_id", "N/A") for t in similar_tickets[:3]]

        return DeepAnalysisResult(
            root_cause=rng.choice(self._ROOT_CAUSES),
            resolution_reasoning=(
                "Analysis of similar resolved incidents indicates this failure mode occurs when "
                "system load exceeds baseline by 3x without corresponding resource scaling. "
                "The resolution pattern involves both immediate mitigation and architectural change."
            ),
            risk_notes=rng.choice(self._RISK_NOTES),
            step_by_step_fix=[
                "1. Apply immediate mitigation: restart affected service replicas",
                "2. Increase resource limits in Kubernetes deployment manifest",
                "3. Deploy configuration change with rolling update strategy",
                "4. Monitor error rate and latency for 30 minutes post-deploy",
                "5. Schedule follow-up architectural review within 1 sprint",
            ],
            related_patterns=[
                "Connection Pool Exhaustion Pattern",
                "Cascading Timeout Failure",
                "Resource Saturation Under Load",
            ],
            confidence_explanation=(
                f"High confidence based on {len(similar_tickets)} similar resolved incidents "
                f"(top match: {related_ids[0] if related_ids else 'N/A'}). "
                "Pattern matches 85% of historical occurrences for this error class."
            ),
            model_version=self.model_version,
            tokens_used=rng.randint(800, 1500),
            raw_response={"mock": True, "model": self.model_version, "related": related_ids},
        )

    async def health_check(self) -> bool:
        return True